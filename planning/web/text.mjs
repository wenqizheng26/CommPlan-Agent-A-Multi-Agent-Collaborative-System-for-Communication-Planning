// Backend spans count Unicode code points, not JavaScript UTF-16 code units.
export function sourceExcerpt(text, span) {
  return Array.from(text).slice(span[0], span[1]).join('');
}

// Display aliases for registered metadata saved before the copy cleanup. Apply only to
// system metadata; task input, source documents, model logs and evidence JSON stay verbatim.
const METADATA_ALIASES=new Map([
 ['老师验收口径的自由空间基本传输损耗','自由空间基本传输损耗'],
 ['老师的三条验收案例','调制灵敏度表（模拟）'],
 ['按计算依赖加入上游登记公式：老师验收口径的自由空间基本传输损耗。','按计算依赖加入上游登记公式：自由空间基本传输损耗。'],
 ['老师链路余量验收工具使用的自由空间路径损耗。频率用 MHz、距离用 km，使用 32.44 常数；单独计算自由空间路径损耗仍用 fspl_ghz，以保持 v0.1.0 的结果。','按自由空间假设计算路径损耗，频率用 MHz、距离用 km，常数取 32.44；用于链路余量计算。'],
 ['32.44 是 20·log10(4π·10⁹/c) 在 c≈3×10⁸ m/s 时取两位小数，未舍入值约为 32.4418；采用精确光速 299792458 m/s 时为 32.4478。常数按老师验收说明取 32.44。','32.44 是 20·log10(4π·10⁹/c) 在 c≈3×10⁸ m/s 时取两位小数，未舍入值约为 32.4418；采用精确光速 299792458 m/s 时为 32.4478。本公式采用 32.44。'],
 ['与 fspl_ghz 的 92.4 相比，换算单位后的结果大约大 0.04 dB。单独算 FSPL 时仍用 fspl_ghz，以保持 v0.1.0 的结果。','与 GHz 形式采用的 92.4 常数相比，统一频率单位后结果约高 0.04 dB。'],
 ['物理关系来自 ITU-R P.525-5，f 为 MHz、d 为 km；常数 32.44 取自老师的验收说明 docs/design/TEACHER_CASES.md（决定 · 公式），不同于标准式(6)的 32.4 舍入常数。','物理关系来自 ITU-R P.525-5，f 为 MHz、d 为 km；常数 32.44 为链路余量计算约定（docs/design/TEACHER_CASES.md · 决定 · 公式），不同于标准式(6)的 32.4 舍入常数。'],
 ['本机无原文，按 2026-09-28 调研时在 ITU 官网核对的内容；ν=h*sqrt((2/λ)*(1/d1+1/d2))，λ=0.299792458/f m，距离从 km 换成 m。','按 ITU 官网核对的公式换算：ν=h*sqrt((2/λ)*(1/d1+1/d2))，λ=0.299792458/f m，距离从 km 换成 m。'],
 ['本机无原文，按 2026-09-28 调研时在 ITU 官网核对的内容；直接使用 J(ν) 的 dB 近似式，输入无量纲。','按 ITU 官网核对的公式，直接使用 J(ν) 的 dB 近似式，输入无量纲。'],
 ['采用球面地球反射点与曲率修正高度，f 为 GHz、d 为 km、h 为 m；式 (126) 使用 0.3 而非精确光速。k 趋向无穷大时回到平地面两径；30 km 演示路径不可忽略曲率。','采用球面地球反射点与曲率修正高度，f 为 GHz、d 为 km、h 为 m；式 (126) 使用 0.3 而非精确光速。k 趋向无穷大时回到平地面两径；30 km 路径不可忽略曲率。']
]);
export function metadataText(text){return METADATA_ALIASES.get(text)??text;}
