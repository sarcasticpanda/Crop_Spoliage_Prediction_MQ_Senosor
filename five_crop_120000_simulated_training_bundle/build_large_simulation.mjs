import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

// Reproducible faculty prototype. Every sensor value and outcome is simulated.
// No coefficient here is a measured shelf-life or calibrated MQ gas response.
const out = path.join(path.dirname(new URL(import.meta.url).pathname), 'large_simulation');
await fs.mkdir(out, {recursive:true});
let seed = 20261012;
function rand() { seed=(Math.imul(1664525,seed)+1013904223)>>>0; return seed/4294967296; }
function normal() { return Math.sqrt(-2*Math.log(Math.max(rand(),1e-12)))*Math.cos(2*Math.PI*rand()); }
function clamp(x,a,b) { return Math.min(b,Math.max(a,x)); }
function rnd(x,n=3) { return Number(x.toFixed(n)); }
function dewPoint(t,h) { const a=17.625,b=243.04,g=Math.log(h/100)+a*t/(b+t); return b*g/(a-g); }
function heatIndex(t,h) {
  if(t<27||h<40) return t; // Explicit illustrative convention; faculty device may differ.
  const f=t*1.8+32;
  const v=-42.379+2.04901523*f+10.14333127*h-.22475541*f*h-.00683783*f*f
    -.05481717*h*h+.00122874*f*f*h+.00085282*f*h*h-.00000199*f*f*h*h;
  return (v-32)/1.8;
}
const crops=[
  {name:'wheat',group:'dry_grain',step:7,base:.00265,k:.060,ref:25,grain:true,mass:[300,6000],defect:'visible_mould_or_insects',conditions:[[15,55],[25,65],[32,65],[32,85]]},
  {name:'maize',group:'dry_grain',step:7,base:.00325,k:.063,ref:25,grain:true,mass:[300,6000],defect:'visible_mould_or_insects',conditions:[[15,55],[25,65],[32,65],[32,85]]},
  {name:'potato',group:'tuber',step:1,base:.022,k:.061,ref:18,grain:false,mass:[100,1800],defect:'soft_rot_or_sprouting',conditions:[[7,95],[18,88],[27,88],[27,97]]},
  {name:'onion',group:'cured_bulb',step:1,base:.019,k:.065,ref:20,grain:false,mass:[100,1800],defect:'rot_or_sprouting',conditions:[[2,68],[20,68],[30,68],[30,84]]},
  {name:'spinach',group:'leafy_vegetable',step:.25,base:.135,k:.071,ref:10,grain:false,mass:[20,300],defect:'wilt_yellow_or_decay',conditions:[[2,96],[10,88],[20,88],[20,99]]}
];
const scenarios=['cool_proper','ambient','warm','warm_humid','ambient_to_cool','ambient_to_warm'];
const mqNames=['MQ2','MQ3','MQ4','MQ5','MQ6','MQ7','MQ8','MQ9','MQ135'];
const headers=[
  'data_origin','crop','crop_group','sim_lot_id','sim_trajectory_id','scenario_SIM','sim_timestamp_utc','storage_age_days',
  'Date','Time','Temperature(°C)','Humidity(%)','Pressure(hPa)','AQI','Gas (kOhms)','Altitude(m)','DewPoint(°C)','HeatIndex(°C)',
  'grain_moisture_pct_SIM','lot_mass_kg_SIM','initial_inspection_defect_pct_SIM','past_mean_temp_C_SIM','past_mean_rh_pct_SIM','past_hot_degree_days_SIM',
  ...mqNames.map(x=>`${x}_response_index_SIM`),
  'inspection_defect_type_SIM','inspection_defect_pct_SIM','status_SIM','failure_interval_start_days_SIM',
  'failure_interval_end_days_SIM','event_observed_SIM','observed_followup_days_SIM','remaining_days_to_first_failed_check_SIM','post_failure_SIM'
];
const ix=Object.fromEntries(headers.map((h,i)=>[h,i]));
const filename='five_crop_120000_ALL_SIMULATED_9MQ.csv';
const fh=await fs.open(path.join(out,filename),'w');
let buffer=headers.join(',')+'\n';
let count=0;
const summary={seed:20261012,rows:0,lots:500,trajectories:3000,per_crop:{},failures:{},statuses:{}};
const examples=[];
const startMs=Date.parse('2030-01-01T00:00:00Z'); // Fictional clock, not a collection date.
for(const crop of crops) {
  summary.per_crop[crop.name]=0; summary.failures[crop.name]=0;
  for(let lotNumber=1;lotNumber<=100;lotNumber++) {
    const lotId=`${crop.name.toUpperCase()}-${String(lotNumber).padStart(3,'0')}`;
    const lot={startDamage:.02+.14*rand(),susceptibility:.60+1.05*rand(),
      tempOffset:normal()*.35,rhOffset:normal()*.65,phase:rand()*6.283,
      moisture:11.5+2.6*rand(),mass:crop.mass[0]+(crop.mass[1]-crop.mass[0])*rand(),
      baseline:Array.from({length:9},()=>.09+normal()*.012),
      channelGain:Array.from({length:9},()=>.83+.34*rand()),
      siteAltitude:55+120*rand(),sitePressure:992+15*rand(),
      offsetDays:(lotNumber-1)%31};
    const noise=Array.from({length:40},()=>({
      temp:normal()*.33,rh:normal()*.8,p:normal()*.24,aqi:normal()*5,gas:normal()*3,
      mq:Array.from({length:9},()=>normal()*.022),inspect:normal()*.5}));
    const initialDefect=clamp(1+15.5*lot.startDamage+noise[0].inspect,0,100);
    for(let si=0;si<scenarios.length;si++) {
      const series=[];
      let damage=lot.startDamage,grainMoisture=lot.moisture,defectPct=0,firstFailure=null;
      let firstFailureLower=null,firstFailureUpper=null;
      let sumTemp=0,sumRh=0,hotExposure=0;
      const trajId=`${lotId}-${scenarios[si]}`;
      for(let step=0;step<40;step++) {
        const day=step*crop.step;
        const phase=step>=13;
        const mode=si<4?si:(phase?(si===4?0:2):1);
        const [nomT,nomH]=crop.conditions[mode];
        const n=noise[step]; // Reuse noise: paired scenarios agree exactly before intervention.
        const temp=clamp(nomT+lot.tempOffset+.55*Math.sin(day*.3+lot.phase)+n.temp,0,40);
        const rh=clamp(nomH+lot.rhOffset+1.0*Math.sin(day*.19+lot.phase)+n.rh,35,99.5);
        if(step>0) {
          if(crop.grain) {
            const equilibrium=13.2+.12*(rh-65);
            grainMoisture=clamp(grainMoisture+.018*crop.step*(equilibrium-grainMoisture),9.0,19.0);
          }
          let rate=crop.base*Math.exp(crop.k*(temp-crop.ref))*lot.susceptibility;
          if(crop.grain) rate*=1+1.6*Math.max(0,grainMoisture-13.5);
          else if(crop.name==='spinach') rate*=1+.048*Math.max(0,94-rh)+.07*Math.max(0,rh-98);
          else if(crop.name==='onion') rate*=1+.058*Math.max(0,rh-75);
          else rate*=1+.027*Math.max(0,91-rh)+.09*Math.max(0,rh-97);
          damage+=crop.step*rate;
          hotExposure+=crop.step*Math.max(0,temp-crop.ref);
        }
        sumTemp+=temp; sumRh+=rh;
        // The inspection measures a monotone defect fraction with observer noise.
        // MQ responses are derived separately from the latent condition and drift.
        defectPct=clamp(Math.max(defectPct,1.0+15.5*damage+n.inspect),0,100);
        const observedDefect=rnd(defectPct,2);
        const status=observedDefect>=15?'spoiled':observedDefect>=7?'warning':'acceptable';
        if(firstFailure===null&&status==='spoiled') {
          firstFailure=day;
          firstFailureLower=Math.max(0,day-crop.step);
          firstFailureUpper=day;
        }
        const state=clamp(damage,0,2.3);
        const fermentation=clamp((state-.25)*.95,0,2)*(crop.grain?.30:crop.name==='onion'?.24:.75);
        const broad=clamp(.08+.58*state,0,1.7);
        const sulfur=clamp((state-.36)*.85,0,1.7)*(crop.name==='onion'?1:.2);
        const amines=clamp((state-.45)*.47,0,1.2)*(crop.name==='spinach'?.5:.22);
        const mix=[.23*broad+.24*fermentation+.10*sulfur,.18*broad+.72*fermentation,
          .08*broad+.09*fermentation,.12*broad+.12*fermentation,.11*broad+.13*fermentation,
          .09*broad+.10*fermentation,.10*broad+.11*fermentation,.11*broad+.13*fermentation,
          .34*broad+.15*fermentation+.22*sulfur+.32*amines];
        const mq=mix.map((x,j)=>rnd(clamp((lot.baseline[j]+x)*lot.channelGain[j]
          +.0019*(rh-65)+.0021*(temp-22)+.000035*day+n.mq[j],.005,2.5),4));
        const p=lot.sitePressure+.7*Math.sin(day*.33+lot.phase)+n.p;
        const aqi=Math.round(clamp(55+6*Math.sin(day*.27)+n.aqi,0,500));
        const envGas=clamp(185+30*Math.sin(day*.16+lot.phase)-.35*(rh-65)+n.gas,10,850);
        const dt=new Date(startMs+lot.offsetDays*86400000+Math.round(day*86400000));
        const ts=dt.toISOString();
        const row=['SIMULATED_ALL',crop.name,crop.group,lotId,trajId,scenarios[si],ts,rnd(day,2),
          ts.slice(0,10),ts.slice(11,19),rnd(temp,2),rnd(rh,2),rnd(p,2),aqi,rnd(envGas,2),
          rnd(lot.siteAltitude,1),rnd(dewPoint(temp,rh),2),rnd(heatIndex(temp,rh),2),
          crop.grain?rnd(grainMoisture,2):'',rnd(lot.mass,1),rnd(initialDefect,2),rnd(sumTemp/(step+1),2),
          rnd(sumRh/(step+1),2),rnd(hotExposure,3),...mq,crop.defect,observedDefect,status];
        series.push({row,day});
      }
      if(firstFailure!==null) summary.failures[crop.name]++;
      for(const item of series) {
        item.row.push(firstFailure===null?'':rnd(firstFailureLower,2),firstFailure===null?'':rnd(firstFailureUpper,2),
          firstFailure===null?0:1,rnd(39*crop.step-item.day,2),
          firstFailure===null?'':rnd(Math.max(0,firstFailure-item.day),2),
          firstFailure!==null&&item.day>firstFailure?1:0);
        if(item.row.length!==headers.length) throw Error('Bad column count');
        buffer+=item.row.join(',')+'\n';
        if(buffer.length>800000) { await fh.write(buffer);buffer=''; }
        count++;summary.per_crop[crop.name]++;
        const status=item.row[ix.status_SIM];
        summary.statuses[status]=(summary.statuses[status]||0)+1;
        if(lotNumber===1&&si===0&&examples.length<8) examples.push(item.row);
      }
    }
  }
}
if(buffer) await fh.write(buffer);
await fh.close();
summary.rows=count;
if(count!==120000) throw Error(`Expected 120000 rows, got ${count}`);
await fs.writeFile(path.join(out,'summary.json'),JSON.stringify(summary,null,2));

// A compact companion workbook explains the full CSV without trying to render
// 120,000 × 40 cells in a single slow workbook.
const wb=Workbook.create();
const overview=wb.worksheets.add('Overview');
overview.showGridLines=false;
overview.getRange('A2').values=[['Five-crop simulated training data']];
overview.getRange('A2').format.font={name:'Arial',size:15,bold:true,color:'#172D40'};
overview.getRange('A4:B9').values=[
  ['Data status','All 120,000 rows are simulated; no paired device recordings or observed outcomes'],
  ['Starting lots',500],['Storage trajectories',3000],['Readings per trajectory',40],
  ['Nine MQ channels','MQ2, MQ3, MQ4, MQ5, MQ6, MQ7, MQ8, MQ9, MQ135'],
  ['Purpose','Test ingestion, grouping, classification, and survival code']
];
overview.getRange('A11:D11').values=[['Crop','Rows','Independent starting lots','Trajectories with inspected failure']];
overview.getRange('A12:D16').values=crops.map(c=>[c.name,summary.per_crop[c.name],100,summary.failures[c.name]]);
overview.getRange('A18:D18').values=[['Status','Rows','Meaning','Use as model feature?']];
overview.getRange('A19:D21').values=[
  ['acceptable',summary.statuses.acceptable||0,'Illustrative defect fraction below 7%','No: this is a target'],
  ['warning',summary.statuses.warning||0,'Illustrative defect fraction 7% to below 15%','No: this is a target'],
  ['spoiled',summary.statuses.spoiled||0,'Illustrative defect fraction at least 15%','No: this is a target']
];
overview.getRange('A23:D23').values=[['Training rule','Group by sim_lot_id; never split the same lot across training and test.','','']];
overview.getRange('A25:D25').values=[['Inference rule','Use only present or past readings. Omit inspection and future failure columns.','','']];
for(const r of ['A11:D11','A18:D18'])overview.getRange(r).format={fill:'#234D65',font:{name:'Arial',bold:true,color:'#FFFFFF',size:10}};
overview.getRange('A4:A9').format.font={name:'Arial',bold:true,size:10};
overview.getRange('A:A').format.columnWidth=29;
overview.getRange('B:B').format.columnWidth=51;
overview.getRange('C:C').format.columnWidth=48;
overview.getRange('D:D').format.columnWidth=42;
overview.getRange('A4:D25').format.rowHeight=23;
const data=wb.worksheets.add('Example rows');
data.showGridLines=false;
data.getRangeByIndexes(0,0,1,headers.length).values=[headers];
data.getRangeByIndexes(1,0,examples.length,headers.length).values=examples;
data.getRangeByIndexes(0,0,1,headers.length).format={fill:'#234D65',font:{name:'Arial',bold:true,color:'#FFFFFF',size:10}};
data.getRangeByIndexes(0,0,1,headers.length).format.rowHeight=42;
data.getRangeByIndexes(0,0,1,headers.length).format.wrapText=true;
data.getRange('A:AP').format.columnWidth=19;
data.freezePanes.freezeRows(1);
wb.recalculate();
const sample=await wb.inspect({kind:'table',range:'Overview!A11:D21',include:'values',tableMaxRows:12,tableMaxCols:4});
await fs.writeFile(path.join(out,'workbook_check.ndjson'),sample.ndjson);
const blob=await wb.render({sheetName:'Overview',range:'A2:D25',scale:1,format:'png'});
await fs.writeFile(path.join(out,'overview.png'),new Uint8Array(await blob.arrayBuffer()));
const xlsx=await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(out,'five_crop_120000_summary.xlsx'));
console.log(JSON.stringify(summary));
