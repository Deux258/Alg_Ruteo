// Edición focalizada de las 36 láminas existentes, conservando objetos nativos.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const root=process.cwd(), packages=process.env.RUNTIME_NODE_MODULES;
if(!packages||!process.env.PRESENTATIONS_SKILL_DIR)throw Error('Configurar runtime y skill Presentations');
const require=createRequire(path.join(packages,'@oai/artifact-tool/package.json'));
const {PresentationFile,FileBlob}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const evidence='evidencia/diagnostico_fase2_2026-10-19';
const read=async file=>JSON.parse((await fs.readFile(path.join(root,file),'utf8')).replace(/^\uFEFF/,''));
const tests=await read(evidence+'/pruebas.json'), ui=await read(evidence+'/interfaz/resultado.json');
const replay=await read(evidence+'/replay/summary.json'), clean=await read(evidence+'/arranque_limpio.json');
if(!tests.successful||!ui.successful||replay.unchanged!==120||replay.contradictions.length)throw Error('La evidencia no acredita cierre');
const source='presentacion/fase2_valparaiso_cierre.pptx';
const sourceHash=crypto.createHash('sha256').update(await fs.readFile(path.join(root,source))).digest('hex');
const deck=await PresentationFile.importPptx(await FileBlob.load(path.join(root,source)));
if(deck.slides.items.length!==36)throw Error('La referencia debe contener 36 láminas');
const temp=path.join(root,'tmp/presentation/diagnostico');await fs.mkdir(temp,{recursive:true});
const changed=[3,14,21,22,35,36];
for(const n of changed){
 const preview=await deck.export({slide:deck.slides.items[n-1],format:'png',scale:1});
 await fs.writeFile(path.join(temp,`before-${n}.png`),new Uint8Array(await preview.arrayBuffer()));
}
const replace=(n,old,value)=>{
 const matches=deck.slides.items[n-1].shapes.items.filter(s=>s.text.toString()===old);
 if(matches.length!==1)throw Error(`Texto no unívoco en ${n}: ${old}`);
 matches[0].text=value;
};
deck.slides.items[2].tables.items[0].cells.set(4,1,`${tests.tests_run} aprobadas, 0 omisiones`);
deck.slides.items[2].tables.items[0].cells.set(5,1,`${clean.duration_s.toFixed(3)} s, nueve salidas`);
replace(14,'Sin escape modelado durante un segmento','A4: aceptación del criterio 5.1 pendiente del docente');
replace(21,'Control viable: 13/120. Sin superioridad estadística demostrada','13/120 admisibles. 120/120 resultados conservados con diagnóstico');
replace(22,'118 pruebas y 13 comprobaciones reales de interfaz',`${tests.tests_run} pruebas y ${ui.checks.length} comprobaciones reales de interfaz`);
replace(22,'Arranque limpio, repetición idempotente y cero duplicados','120/120 resultados idénticos. Oráculo sin contradicciones');
replace(22,'S1–S7 más S1H complementaria, con originales verificables','S6: tres intentos fallidos por DNS dentro de Docker');
replace(22,'DSM y AIP reutilizados; consulta oficial no disponible','Snapshot AIP validado. Actualización completa bloqueada');
replace(22,'Despeje vertical y autonomía energética real sin verificar','A4 pendiente docente. Despeje vertical sin verificar');
replace(22,'Paquete listo para carga manual en GitLab UDP y Canvas','Git conectado. Canvas: carga manual del equipo');
replace(35,'Fixture sintético independiente de la BD. A2 real permanece vacío. Las clases históricas no son fuego activo.',
 'A4 sintético: desactivada admite clase 5. Límite 4 admite clase 1, excluye clase 5 y excluye sin cobertura. Datos históricos separados de fuego activo.');
replace(36,'Anexo · fallos, replanificación y límites','Anexo · causas simultáneas y contraste');
const c=replay.simultaneous_case_counts, p=replay.primary_reasons;
const rows=[['Motivo / comprobación','Principal / simultáneos, sobre 120'],
 ['Extremo AIP',`${p.endpoint_blocked} / ${c.aip_endpoint_restriction}`],
 ['Sin cobertura histórica',`${p.historical_class_unknown} / ${c.historical_class_unknown}`],
 ['Presupuesto insuficiente',`${p.insufficient_return_budget} / ${c.insufficient_return_budget}`],
 ['Meteorología fuera de perfil',`${p.weather_outside_profile} / ${c.weather_outside_profile}`],
 ['Misión admisible','13 / 120 casos']];
for(let r=0;r<rows.length;r++)for(let col=0;col<2;col++)deck.slides.items[35].tables.items[0].cells.set(r,col,rows[r][col]);
replace(36,'Replanificar conserva tiempo consumido y regreso. Un cierre durante el segmento interrumpe la misión.',
 'Las causas coinciden: no sumar simultáneos. 44 casos sin ida o retorno admitidos. Dijkstra independiente contrasta presupuesto y observación en esta malla.');
for(const slide of deck.slides.items)slide.speakerNotes.text+='\n\nActualización de diagnóstico: '+evidence+
 '\nRun: '+replay.run_id+'\nCódigo: '+tests.software.code_sha256+
 '\n120 solicitudes idénticas al plan conservado; no se actualizaron fuentes activas. '+
 'Adquisición completa bloqueada por DNS de DGAC. https://aipchile.dgac.gob.cl/aip/vol1/seccion/enr . '+
 'A4: política preventiva opcional; consulta docente preparada y no enviada.';
const candidate=path.join(temp,'candidate.pptx');
await(await PresentationFile.exportPptx(deck)).save(candidate);
const skill=process.env.PRESENTATIONS_SKILL_DIR;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const owners=[3,5,8,9,10,11,12,13,14,15,18,19,21,23,24,35,36];
const final=path.join(root,'presentacion/fase2_valparaiso_diagnostico.pptx');
await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:final,
 pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',...owners.flatMap(n=>['--require-native-table-slide',String(n)])],
 explicitTotalSlideCount:36,requiredNativeTableOwnerSlides:owners,
 fontPolicy:{basis:'reference',families:['Arial'],referencePath:path.join(root,source),referenceSha256:sourceHash},
 verifyArtifactToolImport:true,receiptPath:path.join(temp,'validation.json')});
const verified=await PresentationFile.importPptx(await FileBlob.load(final));
for(const [i,slide]of verified.slides.items.entries()){
 const image=await verified.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(temp,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await image.arrayBuffer()));
}
console.log(JSON.stringify({output:final,slides:36,changed,code_sha256:tests.software.code_sha256}));
