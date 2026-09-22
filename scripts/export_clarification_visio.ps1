$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$destination = Join-Path $repoRoot 'docs\diagrams\visio-demo'
$visio = $null
$document = $null
function Style-Node($shape, [string]$fill) {
    $shape.CellsU('FillForegnd').FormulaU = $fill
    $shape.CellsU('LineColor').FormulaU = 'RGB(90,127,119)'
    $shape.CellsU('LineWeight').FormulaU = '1 pt'
    $shape.CellsU('Char.Font').FormulaU = 'FONT("Microsoft YaHei")'
    $shape.CellsU('Char.AsianFont').FormulaU = 'FONT("Microsoft YaHei")'
    $shape.CellsU('Char.Size').FormulaU = '12 pt'
    $shape.CellsU('Char.Color').FormulaU = 'RGB(27,57,54)'
    $shape.CellsU('Para.HorzAlign').FormulaU = '1'
    $shape.CellsU('VerticalAlign').FormulaU = '1'
}
try {
    $visio = New-Object -ComObject Visio.InvisibleApp
    $visio.AlertResponse = 7
    $document = $visio.Documents.Add('')
    $document.Title = '需求确认与补充：当前受控工作流'
    $page = $document.Pages.Item(1)
    $page.Name = '需求澄清与区间计算'
    $page.PageSheet.CellsU('PageWidth').FormulaU = '13 in'
    $page.PageSheet.CellsU('PageHeight').FormulaU = '10 in'
    $title = $page.DrawRectangle(0.4,8.95,12.6,9.75)
    $title.Text = "通信筹划：需求确认与补充`n当前实现 · 明确区间 / 离散候选 · 确认后计算"
    Style-Node $title 'RGB(255,255,255)'
    $title.CellsU('LinePattern').FormulaU = '0'
    $title.CellsU('Char.Size').FormulaU = '19 pt'
    $nodes = @{}
    $specs = @(
        @('input',4.9,7.95,8.1,8.65,"用户输入需求`n原话、条件与来源"),
        @('parse',4.9,6.65,8.1,7.45,"需求与规划 Agent`n识别目标、缺项、冲突及近似表达"),
        @('clarify',0.45,4.95,4.05,6.0,"需求确认与补充`n先目标、后参数；多个问题集中展示`n部分回答保留，未解决问题继续等待"),
        @('gate',4.9,5.05,8.1,5.95,"仍有未解决问题？`n明确区间 / 候选不算歧义"),
        @('gap',9.0,5.05,12.55,5.95,"需求明确但能力不足`n说明缺口，停止计算"),
        @('confirm',4.9,3.75,8.1,4.55,"用户核对并确认当前版本`n单值、上下界或离散候选均保留"),
        @('compute',4.9,2.4,8.1,3.3,"计算 Agent → 确定性公式`n区间端点计算；候选分别执行`n最多 64 组端点 / 候选组合"),
        @('review',9.0,2.4,12.55,3.3,"硬校验与结构化审查`n核对输入、端点、结果与来源"),
        @('publish',9.0,0.95,12.55,1.85,"发布结果与证据`n计算范围非置信区间`n仅自由空间单链路基准"),
        @('state',0.45,1.3,4.05,3.3,"共享状态 / SQLite 检查点`n问题标识、回答原文与历史版本`n支持刷新与服务重启恢复`n修改输入使旧确认与结果失效")
    )
    foreach ($spec in $specs) {
        $node = $page.DrawRectangle($spec[1],$spec[2],$spec[3],$spec[4])
        $node.NameU = $spec[0]
        $node.Text = $spec[5]
        Style-Node $node $(if($spec[0] -eq 'clarify'){'RGB(255,247,225)'}else{'RGB(239,247,242)'})
        $nodes[$spec[0]] = $node
    }
    $edges = @(
        @('input','parse',0.5,0,0.5,1),@('parse','gate',0.5,0,0.5,1),
        @('gate','clarify',0,0.5,1,0.5),@('clarify','parse',0.5,1,0,0.5),
        @('gate','gap',1,0.5,0,0.5),@('gate','confirm',0.5,0,0.5,1),
        @('confirm','compute',0.5,0,0.5,1),@('compute','review',1,0.5,0,0.5),
        @('review','publish',0.5,0,0.5,1),@('clarify','state',0.5,0,0.5,1)
    )
    foreach($edge in $edges) {
        $line = $page.DrawLine(0,0,1,1)
        $line.CellsU('BeginX').GlueToPos($nodes[$edge[0]],$edge[2],$edge[3])
        $line.CellsU('EndX').GlueToPos($nodes[$edge[1]],$edge[4],$edge[5])
        $line.CellsU('EndArrow').FormulaU = '4'
        $line.CellsU('LineColor').FormulaU = 'RGB(90,127,119)'
        $line.CellsU('LineWeight').FormulaU = '1.2 pt'
    }
    foreach($label in @(@(4.1,5.55,4.85,5.85,'需澄清'),@(8.12,5.55,8.98,5.85,'不支持'),@(6.55,4.65,8.15,4.95,'明确且支持'),@(2.6,6.8,4.2,7.15,'回答后重评'))){
        $caption=$page.DrawRectangle($label[0],$label[1],$label[2],$label[3]);$caption.Text=$label[4]
        Style-Node $caption 'RGB(255,255,255)';$caption.CellsU('LinePattern').FormulaU='0';$caption.CellsU('Char.Size').FormulaU='10 pt'
    }
    $foot=$page.DrawRectangle(0.45,0.12,12.55,0.7)
    $foot.Text='受控主控按状态调度；审查退回进入新一轮确认。每版本最多两次计算。区间计算不推断概率、置信度或真实海上传播。'
    Style-Node $foot 'RGB(255,255,255)'
    $foot.CellsU('LinePattern').FormulaU='0'
    $foot.CellsU('Char.Size').FormulaU='10 pt'
    $file=Join-Path $destination 'clarification-workflow.vsdx'
    $document.SaveAs($file)
    $page.Export((Join-Path $destination 'clarification-workflow.png'))
    $document.Saved=$true
    Write-Output "Saved native Visio and exported PNG: $file"
} finally {
    if($null -ne $document){$document.Saved=$true;$document.Close()}
    if($null -ne $visio){$visio.Quit();[Runtime.InteropServices.Marshal]::FinalReleaseComObject($visio)|Out-Null}
}
