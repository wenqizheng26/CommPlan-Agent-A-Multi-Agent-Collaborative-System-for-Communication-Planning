"""Trusted command boundary for a local, serialized, durable planning slice."""
import copy
from pathlib import Path
import re
from langgraph.types import Command
from formula_rag.catalog import load_catalog
from planning.agents.requirements import RequirementsAgent
from planning.requirements_contract import digest, require, obj, revision, validate_request, strict_json
from planning.services.confirmation import confirm_review
from planning.services.requirement_evidence import snapshot_for
from planning.workflow.planning_graph import build_planning_graph
from planning.workflow.task_store import TaskStore
from planning.workflow.requirements_graph import stamp
from planning.workflow.activity import ActivityStore, observe
from planning.services.supplement import merge_supplement, conversation_of, edited_conversation


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value) is not None,'INVALID_ID')


def validate_command(command):
    require(type(command) is dict,'COMMAND_OBJECT_REQUIRED')
    action=command.get('action')
    require(type(action) is str and action in {'create','edit','supplement','confirm','cancel'},'INVALID_ACTION')
    fields='action task_id event_id expected_revision expected_state_version'
    if action in {'create','edit'}:
        fields+=' input mode'
    if action=='confirm':
        fields+=' review_hash'
    if action=='supplement':
        fields+=' message mode'
    obj(command,fields)
    identifier(command['task_id']); identifier(command['event_id'])
    revision(command['expected_revision']); revision(command['expected_state_version'])
    if action in {'create','edit'}:
        obj(command['input'],'raw_text manual_parameters condition target')
        require(type(command['mode']) is str and command['mode'] in {'deterministic','llm'},'INVALID_MODE')
        validate_request(dict(schema_version='1.0.0',task_id=command['task_id'],revision=command['expected_revision'],
                              request_id=command['event_id'],**command['input']))
    if action=='confirm':
        require(type(command['review_hash']) is str and len(command['review_hash'])<=100,'INVALID_REVIEW_HASH')
    if action=='supplement':
        require(type(command['message']) is str and 0<len(command['message'].strip())<=2000,'INVALID_SUPPLEMENT')
        require(command['mode'] in {'deterministic','llm'},'INVALID_MODE')
    digest(command)
    return copy.deepcopy(command)


class TaskService:
    def __init__(self, root, db_path):
        self.root=Path(root)
        self.store=TaskStore(db_path)
        self.activity=ActivityStore(db_path)

    def get(self, task_id):
        identifier(task_id)
        return self.store.get(task_id)

    def history(self, task_id):
        identifier(task_id)
        return self.store.history(task_id)

    def apply(self, command):
        c=validate_command(command)
        run=None
        try:
            run=self.activity.start(c)
        except Exception:
            pass
        observer=lambda node, phase, details: self.activity.append(run,node,phase,details)
        try:
            result=self._apply(c,observer)
        except BaseException as exc:
            try:
                self.activity.finish(run,'rejected',error=type(exc).__name__)
            except Exception:
                pass
            raise
        # _apply returns only AFTER the task/checkpoint transaction has committed.
        observe(observer,'state','completed',caller='orchestrator',operation='commit')
        observe(observer,'orchestrator','completed',caller='input',mode='bounded_policy')
        try:
            self.activity.finish(run,'replayed' if result['replayed'] else 'committed',
                                 status=result['state']['status'],state_version=result['state']['state_version'])
        except Exception:
            pass
        return result

    def _apply(self, c, observer):
        task_id, event_id, action=c['task_id'],c['event_id'],c['action']
        payload_hash=digest(c)
        observe(observer,'orchestrator','started',caller='input',mode='bounded_policy')
        observe(observer,'state','started',caller='orchestrator',operation='read')
        with self.store.transaction() as (conn,saver):
            current=self.store.get_in(conn,task_id)
            observe(observer,'state','completed',caller='orchestrator',operation='read')
            recorded=conn.execute('SELECT payload_hash,ack FROM events WHERE task_id=? AND event_id=?',(task_id,event_id)).fetchone()
            if recorded:
                require(recorded[0]==payload_hash,'IDEMPOTENCY_CONFLICT')
                return dict(state=current,acknowledgement=strict_json(recorded[1]),replayed=True)
            if action=='create':
                require(current is None,'TASK_EXISTS')
                require(c['expected_revision']==0,'STALE_REVISION')
                require(c['expected_state_version']==0,'STALE_STATE_VERSION')
                rev,version=0,1
            else:
                require(current is not None,'TASK_NOT_FOUND')
                require(c['expected_revision']==current['revision'],'STALE_REVISION')
                require(c['expected_state_version']==current['state_version'],'STALE_STATE_VERSION')
                rev=current['revision']+(1 if action in {'edit','supplement'} else 0)
                version=current['state_version']+1
            mode=c['mode'] if action in {'create','edit','supplement'} else current['mode']
            conversation=conversation_of(current) if current else None
            if action=='supplement':
                observe(observer,'requirements','started',caller='orchestrator',purpose='supplement')
                next_input,conversation=merge_supplement(current,c['message'],event_id,mode,observer=observer)
            elif action in {'create','edit'}:
                next_input=c['input']
                conversation=edited_conversation(current,next_input,event_id) if current else dict(
                    original_input=copy.deepcopy(next_input),turns=[],pending=[],field_sources={})
            # Rebuilding the agent loads the current knowledge directory. Confirmation
            # resumes after requirements, so intent parsing is not repeated.
            # Calculation and review may make their own bounded model calls.
            if action!='cancel': observe(observer,'knowledge','started',caller='rag',operation='load_catalog')
            cards=[] if action=='cancel' else load_catalog(self.root)
            agent=None if action=='cancel' else RequirementsAgent(self.root,selector=False if mode=='deterministic' else None)
            if agent is not None:
                require(agent.cards==cards,'KNOWLEDGE_CHANGED')
                agent.observer=observer
                observe(observer,'knowledge','completed',caller='rag',operation='load_catalog')
            graph=build_planning_graph(agent,saver,cards,observer=observer,
                pending_questions=[p['question'] for p in (conversation or {}).get('pending',[])])
            config={'configurable':{'thread_id':f'{task_id}:r{rev}'},'recursion_limit':24}
            if action in {'create','edit','supplement'}:
                request=dict(schema_version='1.0.0',task_id=task_id,revision=rev,request_id=event_id,**next_input)
                initial=dict(request=request,report=None,review=None,confirmed_snapshot=None,result=None,
                             validations=[],final_report=None,status='RECEIVED',trace=[],failure=None,
                             calculation_role=None,review_assessment=None,calculation_attempts=0,
                             execution_results=[],review_history=[],calculation_roles=[],routing_decisions=[],routed_action='')
                output=graph.invoke(initial,config,durability='sync')
            elif action=='confirm':
                require(current['status']=='AWAITING_CONFIRMATION','NOT_CONFIRMABLE')
                require(not conversation['pending'],'UNRESOLVED_SUPPLEMENT')
                require(c['review_hash']==current['review']['review_hash'],'REVIEW_HASH_MISMATCH')
                require(current['report']['knowledge_snapshot']==snapshot_for(cards),'KNOWLEDGE_CHANGED')
                snapshot=confirm_review(current['review'],cards)
                saved=graph.get_state(config)
                require(saved.values['review']==current['review'] and saved.next==('human_confirmation',),'CHECKPOINT_STATE_MISMATCH')
                output=graph.invoke(Command(resume={'action':'confirm','snapshot':snapshot}),config,durability='sync')
            elif current['status']=='AWAITING_CONFIRMATION':
                output=graph.invoke(Command(resume={'action':'cancel'}),config,durability='sync')
            else:
                require(current['status'] in {'AWAITING_INPUT','NEEDS_MODEL','FAILED'},'NOT_CANCELLABLE')
                output={k:copy.deepcopy(current[k]) for k in ('request','report','review','confirmed_snapshot','result','validations','final_report','status','trace','failure')}
                for key in ('calculation_role','review_assessment','calculation_attempts','execution_results',
                            'review_history','calculation_roles','routing_decisions','routed_action'):
                    if key in current: output[key]=copy.deepcopy(current[key])
                output.update(status='CANCELLED',failure=None)
                graph.update_state(config,output)
            pending=[dict(id=i.id,value=i.value) for i in output.pop('__interrupt__',())]
            state=dict(output,schema_version='1.0.0',profile='confirmed-fspl-loop-v1',task_id=task_id,
                       revision=rev,state_version=version,mode=mode,pending_interrupt=pending,updated_at=stamp(),
                       conversation=conversation)
            ack=dict(task_id=task_id,event_id=event_id,revision=rev,state_version=version,status=state['status'])
            observe(observer,'state','started',caller='orchestrator',operation='save')
            self.store.save(conn,state,event_id,payload_hash,ack)
            return dict(state=state,acknowledgement=ack,replayed=False)
