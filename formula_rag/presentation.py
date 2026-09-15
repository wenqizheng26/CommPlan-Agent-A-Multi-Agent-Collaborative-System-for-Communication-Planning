"""Derive mathematical display from the same AST used by the calculator."""
import ast
from .parsing import FIELDS

SYMBOLS = {
    'bit_rate_bps': r'R_{\mathrm{b}}', 'ebn0_db': r'\gamma_{\mathrm{b}}',
    'engineering_loss_db': r'L_{\mathrm{impl}}', 'noise_figure_db': r'F_{\mathrm{n}}',
    'noise_density_dbm_hz': r'N_0',
    'frequency_ghz': 'f', 'distance_km': 'd', 'speed_kmh': 'v',
    'temperature_k': 'T', 'bandwidth_hz': 'B',
    'tx_power_dbm': r'P_{\mathrm{t}}', 'rx_power_dbm': r'P_{\mathrm{r}}',
    'tx_gain_dbi': r'G_{\mathrm{t}}', 'rx_gain_dbi': r'G_{\mathrm{r}}',
    'tx_loss_db': r'L_{\mathrm{t}}', 'rx_loss_db': r'L_{\mathrm{r}}',
    'path_loss_db': r'L_{\mathrm{p}}', 'extra_loss_db': r'L_{\mathrm{e}}',
    'rx_threshold_dbm': r'P_{\mathrm{min}}', 'reserve_db': r'M_{\mathrm{reserve}}',
    'maximum_doppler_hz': r'f_{\mathrm{D,max}}', 'noise_power_dbm': r'N',
    'link_margin_db': r'M', 'pi': r'\pi',
}


def symbol(name):
    return SYMBOLS.get(name, r'\mathrm{' + name.replace('_', r'\_') + '}')


def expression_latex(expression):
    def wrap(text):
        return r'\left(' + text + r'\right)'

    def render(node):
        if isinstance(node, ast.Name):
            return symbol(node.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            value = str(node.value)
            if 'e' in value.lower():
                mantissa, exponent = value.lower().split('e')
                return mantissa + r'\times 10^{' + str(int(exponent)) + '}'
            return value
        if isinstance(node, ast.UnaryOp):
            operand = render(node.operand)
            if isinstance(node.operand, ast.BinOp):
                operand = wrap(operand)
            return ('-' if isinstance(node.op, ast.USub) else '+') + operand
        if isinstance(node, ast.BinOp):
            left, right = render(node.left), render(node.right)
            if isinstance(node.op, ast.Div):
                return r'\frac{' + left + '}{' + right + '}'
            if isinstance(node.op, ast.Pow):
                return '{' + wrap(left) + '}^{' + right + '}'
            if isinstance(node.op, ast.Mult):
                if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, (ast.Add, ast.Sub)):
                    left = wrap(left)
                if isinstance(node.right, ast.BinOp) and isinstance(node.right.op, (ast.Add, ast.Sub)):
                    right = wrap(right)
                return left + r'\,\cdot\,' + right
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if isinstance(node.op, ast.Sub) and isinstance(node.right, ast.BinOp) and isinstance(node.right.op, (ast.Add, ast.Sub)):
                    right = wrap(right)
                return left + (' + ' if isinstance(node.op, ast.Add) else ' - ') + right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1:
            arg = render(node.args[0])
            if node.func.id == 'sqrt':
                return r'\sqrt{' + arg + '}'
            if node.func.id == 'abs':
                return r'\left|' + arg + r'\right|'
            functions = {'log10': r'\log_{10}', 'ln': r'\ln', 'sin': r'\sin', 'cos': r'\cos'}
            if node.func.id in functions:
                return functions[node.func.id] + wrap(arg)
        raise ValueError('不支持的公式展示表达式')
    return render(ast.parse(expression, mode='eval').body)


def formula_view(card):
    return {
        'latex': symbol(card['output']['name']) + ' = ' + expression_latex(card['expression']),
        'output_unit': card['output']['unit'],
        'symbols': [{'field': k, 'latex': symbol(k), 'label': FIELDS.get(k, (s['description'],))[0],
                     'unit': s['unit'], 'description': s['description']} for k, s in card['parameters'].items()],
    }
