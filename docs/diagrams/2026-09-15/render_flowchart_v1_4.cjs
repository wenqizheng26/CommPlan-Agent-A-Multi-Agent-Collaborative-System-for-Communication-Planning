const sharp = require('C:/Users/nntm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const path = require('path');
const base = __dirname;
sharp(path.join(base,'通信筹划协同流程_v1.4.svg')).png().toFile(path.join(base,'通信筹划协同流程_v1.4.png')).then(info=>console.log(JSON.stringify(info))).catch(err=>{console.error(err);process.exit(1)});
