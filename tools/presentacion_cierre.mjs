import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const packages = process.env.RUNTIME_NODE_MODULES;
if (!packages)
  throw Error("Configurar RUNTIME_NODE_MODULES con las dependencias de Codex");
const require = createRequire(
  path.join(packages, "@oai/artifact-tool/package.json"),
);
const { PresentationFile, FileBlob } = await import(
  pathToFileURL(require.resolve("@oai/artifact-tool")).href
);
const skill = process.env.PRESENTATIONS_SKILL_DIR;
if (!skill) throw Error("Configurar PRESENTATIONS_SKILL_DIR");
const evidence = "evidencia/cierre_fase2_2026-10-19";
const json = async (file) =>
  JSON.parse(
    (await fs.readFile(path.join(root, file), "utf8")).replace(/^\uFEFF/, ""),
    (key, value, context) =>
      typeof value === "number" &&
      Number.isInteger(value) &&
      !Number.isSafeInteger(value)
        ? context.source
        : value,
  );
const tests = await json(evidence + "/pruebas.json"),
  clean = await json(evidence + "/arranque_limpio.json");
const ui = await json(evidence + "/interfaz/resultado.json");
const experimentDir = (await fs.readdir(path.join(root, evidence))).find((n) =>
  n.startsWith("experiment_"),
);
if (!experimentDir) throw Error("Falta lote completo en evidencia");
const batch = await json(evidence + "/" + experimentDir + "/summary.json");
const summary = batch.summary,
  examples = await json(evidence + "/json_examples.json"),
  schema = await json(evidence + "/schema.json");
const source = "presentacion/fase2_valparaiso.pptx";
const sourceHash = crypto
  .createHash("sha256")
  .update(await fs.readFile(path.join(root, source)))
  .digest("hex");
const deck = await PresentationFile.importPptx(
  await FileBlob.load(path.join(root, source)),
);
if (deck.slides.items.length !== 22)
  throw Error("Se esperan las 22 diapositivas de referencia");
const common = `Run ${batch.run_id}\nCódigo: ${tests.software.code_sha256}\nLote: ${batch.experiment_sha256}\nFuentes y evidencia: ${evidence}.\nLa comparación es estática y sintética. Despeje vertical sin verificar.`;
const text = (s, value, x, y, w, h, size = 24, bold = false) => {
  const shape = s.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  shape.text = value;
  shape.text.style = {
    typeface: "Arial",
    fontSize: size,
    bold,
    color: "#233e43",
  };
  return shape;
};
const replace = (index, old, value) => {
  const matches = deck.slides.items[index].shapes.items.filter(
    (s) => s.text.toString() === old,
  );
  if (matches.length !== 1)
    throw Error(`Texto no unívoco en slide ${index + 1}: ${old}`);
  matches[0].text = value;
};
for (const s of deck.slides.items) {
  for (const sh of s.shapes.items) {
    if (sh.text.toString().startsWith("Valparaíso · Fase2"))
      sh.text.replace("/22", "/36");
  }
  s.speakerNotes.text = s.speakerNotes.text + "\n\n" + common;
}
const table3 = deck.slides.items[2].tables.items[0];
table3.cells.set(4, 1, `${tests.tests_run} aprobadas, 0 omisiones`);
table3.cells.set(5, 1, clean.duration_s.toFixed(3) + " s");
replace(
  2,
  "Hashes de dependencias y pip check en Docker y CI",
  "Hashes y pip check en Docker. CI configurado, pendiente en GitLab.",
);
replace(
  12,
  "WHERE run_id = la publicación verificada",
  `WHERE run_id = '${batch.run_id}'::uuid;`,
);
deck.slides.items[13].tables.items[0].cells.set(
  4,
  1,
  "Clase superior al límite: exclusión preventiva opcional",
);
deck.slides.items[13].speakerNotes.text +=
  "\nA4 expresa política preventiva simulada, no incendio activo. Sin cobertura se excluye por información desconocida. La interpretación docente sigue pendiente.";
deck.slides.items[14].tables.items[0].cells.set(
  4,
  1,
  "1200 s, 8 m/s, desvío 1–1,20 y clase opcional 1–5",
);
text(
  deck.slides.items[14],
  "Historia predeterminada: desactivada (null). Límite opcional 1–5.",
  64,
  540,
  1152,
  45,
  24,
);
text(
  deck.slides.items[14],
  "Sin preferencias: 1200 s, viento menor a 8 m/s y desvío 1,20.",
  64,
  595,
  1152,
  45,
  24,
);
replace(
  18,
  "Dos misiones propuestas por tiempo y exposición",
  "Dos misiones propuestas",
);
for (const index of [17, 18])
  text(
    deck.slides.items[index],
    "Idas muy próximas: rutas distintas no implican corredores independientes.",
    510,
    648,
    700,
    26,
    17,
  );
for (const s of deck.slides.items)
  for (const sh of s.shapes.items) {
    sh.text.replace("de800 m", "de 800 m");
    sh.text.replace("y3 retornos", "y 3 retornos");
    sh.text.replace("y1.20 del", "y 1,20 del");
    sh.text.replace(
      "33 de100 m, 33 de250 m y33 de500 m",
      "33 de 100 m, 33 de 250 m y 33 de 500 m",
    );
  }
replace(
  16,
  "Exclusión de arcos completos por FIRMS, AIP y bloqueos",
  "Exclusiones FIRMS, AIP, bloqueos y política histórica opcional",
);
replace(
  19,
  "100 escenarios: control y99 cierres circulares",
  "100 escenarios por caso y 120 casos predefinidos",
);
replace(
  20,
  "Comparación del caso documentado",
  "Comparación de 120 casos predefinidos",
);
const table21 = deck.slides.items[20].tables.items[0];
[
  ["Método", "Media conjunto", "Dos opciones", "Control viable"],
  ...["reference", "proposed"].map((m) => [
    m === "reference" ? "Dijkstra" : "Propuesto",
    (100 * summary.methods[m].mean_set_survival).toFixed(2) + " %",
    String(summary.methods[m].two_options) + "/120",
    String(summary.methods[m].control_admissible) + "/120",
  ]),
].forEach((r, i) => r.forEach((v, j) => table21.cells.set(i, j, v)));
replace(
  20,
  "100 escenarios válidos, 0 desconocidos",
  `${summary.valid_case_scenarios} escenarios válidos, ${summary.unknown_cases} casos desconocidos`,
);
replace(
  20,
  "ΔR =0 puntos porcentuales",
  `ΔR medio ${summary.mean_delta_pp.toFixed(2)} pp (default +0,03 y clase 4 +3,27)`,
);
replace(
  20,
  "Ambos métodos obtienen las mismas opciones en este caso",
  `${summary.improvements} mejoras, ${summary.ties} empates y ${summary.worsenings} empeoramientos`,
);
replace(
  20,
  "No demuestra superioridad ni probabilidad real de éxito",
  "Control viable: 13/120. Sin superioridad estadística demostrada",
);
replace(
  21,
  "111 pruebas y11 comprobaciones reales de interfaz",
  `${tests.tests_run} pruebas y ${ui.checks.length} comprobaciones reales de interfaz`,
);
replace(
  21,
  "DSM y AIP reutilizados explícitamente; DNS de DGAC bloqueado",
  "DSM y AIP reutilizados; consulta oficial no disponible",
);
replace(
  21,
  "Entrega en GitLab UDP y Canvas pendiente del equipo",
  "Paquete listo para carga manual en GitLab UDP y Canvas",
);
deck.slides.items[20].speakerNotes.text +=
  "\nCinco bases, cuatro objetivos extremos UTM, primera/central/última hora posterior a adquisición, dos perfiles. Se fijan sin calcular factibilidad. Solo 13 casos propuestos tienen control admisible; no es una probabilidad de éxito real.\n" +
  JSON.stringify(batch.by_profile);

const annexes = [];
function slide(title) {
  const s = deck.slides.add();
  s.background.fill = "#f7faf8";
  text(s, title, 64, 42, 1152, 90, 40, true);
  text(
    s,
    `Valparaíso · Fase2 · ${deck.slides.items.length}/36`,
    64,
    675,
    1152,
    24,
    16,
  );
  s.speakerNotes.text = common;
  return s;
}
function table(
  s,
  values,
  { size = 21, widths = [320, 832], height = 440 } = {},
) {
  const rows = values.length,
    columns = values[0].length;
  const t = s.tables.add({
    rows,
    columns,
    left: 64,
    top: 150,
    width: 1152,
    height,
    columnWidths: widths,
    values,
  });
  t.cells
    .block({ row: 0, column: 0, rowCount: rows, columnCount: columns })
    .assign({
      fill: "#ffffff",
      textStyle: { typeface: "Arial", fontSize: size, color: "#233e43" },
      margins: { left: 8, right: 8, top: 4, bottom: 4 },
    });
  t.cells
    .block({ row: 0, column: 0, rowCount: 1, columnCount: columns })
    .assign({
      fill: "#dcebe2",
      textStyle: {
        typeface: "Arial",
        fontSize: size,
        bold: true,
        color: "#233e43",
      },
    });
  t.borders.assign({ fill: "#c5d6cf", width: 1 });
  return t;
}
const names = [...new Set(schema.schema.map((r) => r.table_name))].sort();
for (let part = 0; part < 2; part++) {
  const selected = part === 0 ? names.slice(0, 15) : names.slice(15);
  const values = [["Entidad", "Clave primaria", "Referencias FK"]];
  for (const name of selected) {
    const constraints = schema.constraints.filter((c) => c.source === name);
    const pk =
      constraints
        .find((c) => c.kind === "p")
        ?.definition.match(/\((.*)\)/)?.[1] || "—";
    values.push([
      name,
      pk.replaceAll("run_id", "run"),
      [
        ...new Set(
          constraints.filter((c) => c.kind === "f").map((c) => c.target),
        ),
      ].join(", ") || "—",
    ]);
  }
  const s = slide("Anexo · esquema completo " + (part + 1) + "/2");
  table(s, values, { size: 18, widths: [320, 340, 492], height: 448 });
  text(
    s,
    "run abrevia run_id. FK cruza a entidades de ambas láminas. Columnas completas en SQL.",
    64,
    640,
    1152,
    26,
    18,
  );
  s.speakerNotes.text +=
    "\nEsquema real de PostgreSQL: 29 tablas, vistas excluidas. Detalle de cada restricción en schema.json y diagrama completo en BD/diagrama_fase2_relaciones.svg.";
  annexes.push({ title: "Esquema " + (part + 1), tables: selected });
}
const sources = {
  I: "Malla aérea derivada de bases y cobertura real",
  M1: "SENAPRED y Bomberos/IDE Chile vía ArcGIS",
  M2: "CONAF/CIREN 2019, cobertura y atributos",
  M3: "Copernicus GLO-30, DSM metros EGM2008",
  M4: "Open-Meteo ECMWF IFS 0.25, UTC y m/s",
  A1: "Derivación de M4 según perfil predeterminado",
  A2: "NASA FIRMS VIIRS NOAA-20, buffer 250 m",
  A3: "DGAC AIP ENR 5.1, exclusión horizontal",
  A4: "SENAPRED recurrencia 2020–2024, clases 1–5",
};
for (const key of ["I", "M1", "M2", "M3", "M4", "A1", "A2", "A3", "A4"]) {
  const e = examples[key],
    s = slide("Anexo · " + key + " · extracción, transformación y carga");
  text(s, sources[key], 64, 145, 1152, 40, 24, true);
  const projection = { dataset_key: key, run_id: e.sample.run_id };
  if (key === "I") {
    projection.nodes = e.sample.nodes.map((n) => ({
      id: n.id,
      kind: n.kind,
      geometry: n.geometry,
    }));
    projection.edges = e.sample.edges.map((n) => ({
      id: n.id,
      source: n.source,
      target: n.target,
      geometry: n.geometry,
    }));
  } else if (key === "M1") {
    projection.records = e.sample.records.map((n) => ({
      provider_id: n.provider_id,
      name: n.name,
      candidate: n.candidate,
      inside_study: n.inside_study,
      geometry: n.geometry,
    }));
  } else if (key === "M2") {
    projection.records = e.sample.records.map((n) => ({
      provider_id: n.provider_id,
      category: n.category,
      clipped_area_ha: n.clipped_area_ha,
      attributes: Object.fromEntries(Object.entries(n.attributes).slice(0, 3)),
    }));
  } else if (key === "M4") {
    projection.records = e.sample.records.map((n) =>
      Object.fromEntries(
        Object.entries(n).filter(
          ([k, v]) => k !== "geometry" && (!v || typeof v !== "object"),
        ),
      ),
    );
  } else
    projection.records = e.sample.records.map((record) =>
      Object.fromEntries(
        Object.entries(record)
          .filter(
            ([k, v]) =>
              k !== "geometry" &&
              k !== "original_record" &&
              k !== "attributes" &&
              k !== "conditions" &&
              (!v || typeof v !== "object"),
          )
          .slice(0, 6),
      ),
    );
  const lines = [
    "{",
    ...Object.entries(projection).map(
      ([k, v], i, a) =>
        "  " +
        JSON.stringify(k) +
        ": " +
        JSON.stringify(v) +
        (i < a.length - 1 ? "," : ""),
    ),
    "}",
  ];
  text(s, lines.join("\n"), 64, 200, 760, 385, lines.length > 20 ? 18 : 21);
  const extraction = e.extract
    .join(" ")
    .replaceAll("{run_id}", "RUN")
    .replaceAll("{output}", "JSON");
  text(s, "ET: " + extraction, 855, 205, 360, 160, 21);
  text(
    s,
    "Carga: " + e.load.join(" ").replaceAll("{output}", "JSON"),
    855,
    380,
    360,
    135,
    21,
  );
  text(s, `${e.count} registros · ${e.output}`, 64, 590, 1152, 35, 22);
  text(
    s,
    "Proyección del JSON real: campos omitidos e IDs BIGINT como texto. Original y SHA en evidencia.",
    64,
    635,
    1152,
    30,
    18,
  );
  s.speakerNotes.text += "\n" + JSON.stringify(e);
  annexes.push({
    title: key,
    projection,
    output: e.output,
    dictionary: e.dictionary,
  });
}
{
  const s = slide("Anexo · SQL Dijkstra ejecutado");
  const code = await fs.readFile(
    path.join(root, evidence, "dijkstra.sql"),
    "utf8",
  );
  const rows = await json(evidence + "/dijkstra_result.json");
  text(
    s,
    code
      .replace(" FROM pgr_dijkstra(", "\nFROM pgr_dijkstra(\n")
      .replace("SELECT id,source,target,", "SELECT id,source,target,\n")
      .replace(" FROM routing.edges", "\nFROM routing.edges")
      .replace(" WHERE run_id", "\nWHERE run_id")
      .replace(" ORDER BY", "\nORDER BY"),
    64,
    155,
    1152,
    330,
    21,
  );
  text(
    s,
    `Resultado: ${rows.length} pasos · costo final ${rows.at(-1)?.agg_cost.toFixed(6)} km`,
    64,
    520,
    1152,
    45,
    25,
    true,
  );
  text(
    s,
    "D2: excluir cada arco de D1 y elegir el camino alternativo de menor longitud. Retorno incluido.",
    64,
    590,
    1152,
    60,
    23,
  );
  s.speakerNotes.text +=
    "\nConsulta y resultado íntegros en dijkstra.sql y dijkstra_result.json. Los ejemplos principales 18–19 conservan el caso retrospectivo anterior como referencia, identificado en sus notas.";
  annexes.push({ title: "SQL Dijkstra", code, steps: rows.length });
}
{
  const s = slide("Anexo · efecto de reglas sobre un segmento");
  table(
    s,
    [
      ["Regla", "Antes", "Después"],
      [
        "Meteorología",
        "1000 m / 10 m/s = 100 s",
        "Viento frontal 2 m/s: 125 s",
      ],
      [
        "FIRMS sintético",
        "Segmento permitido",
        "Intersección buffer 250 m: excluir",
      ],
      ["AIP sintético", "Sin intersección", "Intersección con zona: excluir"],
      [
        "Historia clase 5",
        "Política desactivada: exposición",
        "Límite 4: excluir por política",
      ],
    ],
    { size: 22, widths: [245, 390, 517], height: 350 },
  );
  text(
    s,
    "Fixture sintético independiente de la BD. A2 real permanece vacío. Las clases históricas no son fuego activo.",
    64,
    535,
    1152,
    90,
    24,
  );
  s.speakerNotes.text +=
    "\nValores ejecutados en segment_examples.json. EPSG:32719, longitud 1000 m; no modifica originales ni crea incendios ficticios.";
  annexes.push({ title: "Efecto de reglas", synthetic: true });
}
{
  const s = slide("Anexo · fallos, replanificación y límites");
  table(
    s,
    [
      ["Resultado propuesto", "Casos del lote"],
      ...Object.entries(summary.methods.proposed.reasons).map(
        ([reason, count]) => [
          reason === "none" ? "Misión admisible" : reason,
          String(count),
        ],
      ),
    ],
    { size: 22, height: 390 },
  );
  text(
    s,
    "Replanificar conserva tiempo consumido y regreso. Un cierre durante el segmento interrumpe la misión.",
    64,
    570,
    1152,
    70,
    24,
  );
  s.speakerNotes.text +=
    "\nPruebas Playwright y suite Docker. Solo 13/120 casos tienen control admisible; no se ocultan las bases o las horas bloqueadas.";
  annexes.push({
    title: "Fallos y replanificación",
    reasons: summary.methods.proposed.reasons,
  });
}
if (deck.slides.items.length !== 36)
  throw Error("El cierre exige 22 principales y 14 anexos");
const tmp = path.join(root, "tmp/presentation/cierre");
await fs.mkdir(tmp, { recursive: true });
const candidate = path.join(tmp, "candidate.pptx");
await (await PresentationFile.exportPptx(deck)).save(candidate);
await fs.writeFile(
  path.join(root, "presentacion/contenido_cierre.json"),
  JSON.stringify(
    {
      source,
      source_sha256: sourceHash,
      main_slides: 22,
      annexes,
      summary: batch.summary,
    },
    null,
    2,
  ),
);
for (const [i, s] of deck.slides.items.entries()) {
  const blob = await deck.export({ slide: s, format: "png", scale: 1 });
  await fs.writeFile(
    path.join(tmp, `slide-${String(i + 1).padStart(2, "0")}.png`),
    new Uint8Array(await blob.arrayBuffer()),
  );
}
const { finalizePresentation } = await import(
  pathToFileURL(path.join(skill, "container_tools/artifact_tool_utils.mjs"))
    .href
);
const owners = [3, 5, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 21, 23, 24, 35, 36];
await finalizePresentation({
  workspaceDir: root,
  candidatePath: candidate,
  finalPath: path.join(root, "presentacion/fase2_valparaiso_cierre.pptx"),
  pythonExecutable: process.env.RUNTIME_PYTHON,
  integrityValidatorPath: path.join(
    skill,
    "container_tools/inspect_presentation_package_integrity.py",
  ),
  layoutValidatorPath: path.join(
    skill,
    "container_tools/inspect_presentation_layout_geometry.py",
  ),
  layoutArgs: [
    "--expected-slide-size-emu",
    "12192000,6858000",
    "--validate-heading-fit",
    ...owners.flatMap((n) => ["--require-native-table-slide", String(n)]),
  ],
  explicitTotalSlideCount: 36,
  requiredNativeTableOwnerSlides: owners,
  fontPolicy: {
    basis: "reference",
    families: ["Arial"],
    referencePath: path.join(root, source),
    referenceSha256: sourceHash,
  },
  verifyArtifactToolImport: true,
  receiptPath: path.join(tmp, "validation.json"),
});
console.log("Cierre: 36 diapositivas");
