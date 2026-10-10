const fs = require('fs');
const ts = require(process.cwd()+'/frontend/node_modules/typescript');
const {pathToFileURL} = require('url');
const os=require('os');
const path=require('path');
(async () => {
 const code=fs.readFileSync('frontend/src/api/client.ts','utf8');
 const compiled=ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ES2020}}).outputText;
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'story16-client-'));
 const modulePath=path.join(temp,'client.mjs');
 fs.writeFileSync(modulePath,compiled);
 const client=await import(pathToFileURL(modulePath).href);
 fs.rmSync(temp,{recursive:true});
 const base={id:17,report_schema_version:'v2',advisory:{should_block:false}};
 let cases=0;
 for(const provenance of [undefined,{version:1},{version:99}]) {
  const data=provenance?{...base,infra_automation_provenance:provenance}:base;
  global.fetch=async()=>({ok:true,status:200,json:async()=>({data,meta:{}})});
  const response=await client.requestEnvelope('/api/v1/reports/17');
  if(response.data.id!==17 || response.data.report_schema_version!=='v2' || response.data.advisory.should_block!==false)throw Error('changed report contract');
  if(provenance && response.data.infra_automation_provenance!==provenance)throw Error('raw client dropped metadata');
  cases++;
 }
 console.log(JSON.stringify({consumer:'actual React requestEnvelope transpiled with installed TypeScript',cases,passed:true,rendered_ui:false}));
})();
