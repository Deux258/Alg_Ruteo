// Metric DSM + local OSM/CONAF geometry. No remote 3D service or token.
export function terrainLighting(mesh) {
  const { width, height, x, y, elevations } = mesh;
  const normals = Array.from({ length: width * height }, () => [0, 0, 0]);
  const point = (i) => [x[i % width], y[Math.floor(i / width)], elevations[i]];
  for (let j = 0; j < height - 1; j++)
    for (let i = 0; i < width - 1; i++) {
      const a = j * width + i, b = a + 1, c = a + width, d = c + 1;
      for (const face of [[a, b, c], [b, d, c]]) {
        if (face.some((k) => !Number.isFinite(elevations[k]))) continue;
        const [p, q, r] = face.map(point), u = q.map((v, k) => v - p[k]), v = r.map((w, k) => w - p[k]);
        const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
        for (const k of face) for (let axis = 0; axis < 3; axis++) normals[k][axis] += n[axis];
      }
    }
  const lighting = normals.map((n) => {
    const len = Math.hypot(...n) || 1;
    const sun = Math.max(0, (-.42 * n[0] - .38 * n[1] + .82 * n[2]) / len);
    const sky = .5 + .5 * (n[2] / len);
    return .52 + .36 * sun + .14 * sky;
  });
  const colorsAt = (position, baseColor = null) => {
    let shade = .68 + .32 * .87;
    if (width > 1 && height > 1) {
      const fx = Math.max(0, Math.min(width - 1, (position[0] - x[0]) / (x[1] - x[0]))), fy = Math.max(0, Math.min(height - 1, (position[1] - y[0]) / (y[1] - y[0])));
      const ix = Math.min(Math.floor(fx), width - 2), iy = Math.min(Math.floor(fy), height - 2), tx = fx - ix, ty = fy - iy;
      const a = iy * width + ix, b = a + 1, c = a + width, d = c + 1;
      shade = tx + ty <= 1 ? (1 - tx - ty) * lighting[a] + tx * lighting[b] + ty * lighting[c] : (1 - ty) * lighting[b] + (tx + ty - 1) * lighting[d] + (1 - tx) * lighting[c];
    }
    const h = position[2], t = Math.max(0, Math.min(1, h / 520)), palette = baseColor || [.54 + .12 * t, .62 + .06 * t, .44 + .05 * t];
    return palette.map((v) => Math.max(0, Math.min(255, Math.round(v * shade * 255))) / 255);
  };
  const gridColors = elevations.map((h, i) => Number.isFinite(h) ? colorsAt(point(i)) : null);
  return { colorsAt, gridColors };
}

export function terrainGridColors(mesh) { return terrainLighting(mesh).gridColors; }

export function routeArrowAnchors(points, spacing = 100) {
  const segments = []; let length = 0;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    if (!a.every(Number.isFinite) || !b.every(Number.isFinite)) continue;
    const distance = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (distance <= .001) continue;
    segments.push({ a, b, start: length, distance }); length += distance;
  }
  if (!segments.length) return [];
  const distances = [Math.min(25, length / 2)];
  for (let s = spacing; s < length - 5; s += spacing) distances.push(s);
  let index = 0;
  return distances.map((s) => {
    while (index < segments.length - 1 && s > segments[index].start + segments[index].distance) index++;
    const { a, b, start, distance } = segments[index], f = (s - start) / distance;
    const position = a.map((v, k) => v + (b[k] - v) * f);
    const ahead = [position[0] + (b[0] - a[0]) / distance * 10, position[1] + (b[1] - a[1]) / distance * 10, position[2] + (b[2] - a[2]) / distance * 10];
    return { position, ahead, distance_m: s };
  });
}

export function projectTerrainPoint(position, camera) {
  const p = [position[0] - camera.origin[0], position[1] - camera.origin[1], position[2]];
  let x, y, depth;
  if (camera.fpv) {
    const v = p.map((n, i) => n - camera.eye[i]);
    const dot = (a, b) => a.reduce((s, n, i) => s + n * b[i], 0);
    const z = dot(v, camera.forward);
    if (z < 1) return { visible: false };
    x = dot(v, camera.right) * camera.focal / camera.aspect / z;
    y = dot(v, camera.up) * camera.focal / z;
    depth = 1.000100005 - 2.000100005 / z;
  } else {
    const v = p.map((n, i) => n - camera.center[i]);
    const rx = Math.cos(camera.yaw) * v[0] - Math.sin(camera.yaw) * v[1];
    const ry = Math.sin(camera.yaw) * v[0] + Math.cos(camera.yaw) * v[1];
    x = rx * camera.scale;
    y = (ry * Math.sin(camera.pitch) + v[2] * Math.cos(camera.pitch)) * camera.scale * camera.aspect;
    depth = (ry * Math.cos(camera.pitch) - v[2] * Math.sin(camera.pitch)) * camera.scale * .15;
  }
  return { x: (x + 1) * camera.width / 2, y: (1 - y) * camera.height / 2,
    depth, visible: Number.isFinite(x + y + depth) && Math.abs(x) <= 1 && Math.abs(y) <= 1 && Math.abs(depth) <= 1 };
}

// Shared verbatim by scene and route programs; CPU annotation projection mirrors it.
const cameraProjection = `uniform vec3 center;uniform vec4 camera;uniform float aspect;uniform bool firstPerson;uniform vec3 eye;uniform vec3 forward;uniform vec3 right;uniform vec3 up;uniform float focal;
vec4 project(vec3 position){if(firstPerson){vec3 p=position-eye;float z=dot(p,forward);return vec4(dot(p,right)*focal/aspect,dot(p,up)*focal,1.000100005*z-2.000100005,z);}vec3 p=position-center;float x=cos(camera.x)*p.x-sin(camera.x)*p.y;float y=sin(camera.x)*p.x+cos(camera.x)*p.y;return vec4(x*camera.z,(y*sin(camera.y)+p.z*cos(camera.y))*camera.z*aspect,(y*cos(camera.y)-p.z*sin(camera.y))*camera.z*.15,1.);}`;

const annotationPaths = {
  drone: '<path d="M5 5l14 14M5 19 19 5" stroke-width="2.8"/><circle cx="5" cy="5" r="4" fill="#fff"/><circle cx="19" cy="5" r="4" fill="#fff"/><circle cx="5" cy="19" r="4" fill="#fff"/><circle cx="19" cy="19" r="4" fill="#fff"/><rect x="9" y="7" width="6" height="10" rx="2" fill="currentColor"/><path d="m12 1-2 4h4Z" fill="currentColor"/>',
  base: '<path d="M3 12 12 4l9 8v9H3Z" fill="#fff" fill-opacity="0.92"/><path d="M8 21v-6a4 4 0 0 1 8 0v6"/><path d="M12 6.8c1.3 2-.5 2.8.4 4.2.7-.3 1.1-1 1.1-1.8 1.9 2.1.9 4.8-1.5 4.8-2.4 0-3.4-2.7-1.5-4.8-.2 1.1.5 1.5.8 2 .5-1.3-.5-2.3.7-4.4Z" fill="#dc2626" stroke="none"/>',
  station: '<path d="M12 2 4 5.5v6.5c0 5 3.4 9.2 8 10.5 4.6-1.3 8-5.5 8-10.5V5.5L12 2Z" fill="#fff" fill-opacity="0.94"/><path d="M12 5.8c1.6 2.5-.8 3.5.5 5.3.9-.4 1.4-1.3 1.4-2.2 2.4 2.6 1.1 6-2 6-3 0-4.2-3.4-1.9-6-.2 1.4.7 1.8 1.1 2.5.7-1.6-.6-2.9.9-5.6Z" fill="#dc2626" stroke="none"/><path d="M16.5 14.5h3l-1.8 3.2h2.1l-3.6 4.3 1.1-3.3h-2.1Z" fill="#d97706" stroke="none"/>',
  fire: '<path d="M13 2c2 6-3 6 1 10 2-1 3-3 3-5 7 8 3 15-5 15C3 22 1 14 8 7c-1 5 2 5 3 7 3-5-2-7 2-12Z"/>',
  threat: '<path d="m12 3 10 18H2Z"/><path d="M12 9v5M12 17v1"/>',
};

export class TerrainView {
  static async create(canvas, mesh, scene, options = {}) {
    const view = new TerrainView(
      canvas,
      mesh,
      scene?.typed_assets ? null : scene,
    );
    try {
      if (scene?.typed_assets) await view.setScene(scene, options);
      return view;
    } catch (error) {
      view.dispose();
      throw error;
    }
  }
  constructor(canvas, mesh, scene) {
    this.canvas = canvas;
    this.mesh = mesh;
    this.scene = { sha256: scene?.sha256 };
    this.yaw = -0.45;
    this.pitch = 0.68;
    this.zoom = 1.7;
    this.lines = [];
    this.marker = null;
    this.groups = {};
    this.visibility = {};
    this.routeBuffers = [];
    this.sceneVersion = 0;
    this.events = new AbortController();
    this.firstPerson = false;
    this.flightPose = null;
    this.fpvYaw = 0;
    this.fpvPitch = -0.32;
    this.fpvDistance = 58;
    this.swathM = 200;
    this.fov = 70;
    this.annotations = [];
    this.annotationNodes = new Map();
    this.droneNote = "";
    this.fireUtm = null;
    this.forbiddenZoneBuffers = [];
    const gl = (this.gl = canvas.getContext("webgl", {
      antialias: true,
      preserveDrawingBuffer: true,
    }));
    if (!gl) throw new Error("WebGL no disponible en este navegador");
    const shader = (type, source) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, source);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
        throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const vs = shader(
      gl.VERTEX_SHADER,
      `attribute vec3 position;attribute vec3 color;varying vec3 tint;${cameraProjection}void main(){gl_Position=project(position);gl_PointSize=13.;tint=color;}`,
    );
    const fs = shader(
      gl.FRAGMENT_SHADER,
      `precision mediump float;varying vec3 tint;uniform float opacity;void main(){gl_FragColor=vec4(tint,opacity>0.0?opacity:1.0);}`,
    );
    const program = (this.program = gl.createProgram());
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(program));
    this.locations = {
      position: gl.getAttribLocation(program, "position"),
      color: gl.getAttribLocation(program, "color"),
      center: gl.getUniformLocation(program, "center"),
      camera: gl.getUniformLocation(program, "camera"),
      aspect: gl.getUniformLocation(program, "aspect"),
      firstPerson: gl.getUniformLocation(program, "firstPerson"),
      eye: gl.getUniformLocation(program, "eye"),
      forward: gl.getUniformLocation(program, "forward"),
      right: gl.getUniformLocation(program, "right"),
      up: gl.getUniformLocation(program, "up"),
      focal: gl.getUniformLocation(program, "focal"),
      opacity: gl.getUniformLocation(program, "opacity"),
    };
    const routeVs = shader(gl.VERTEX_SHADER, `attribute vec3 routeStart;attribute vec3 routeEnd;attribute vec2 corner;uniform vec2 viewport;uniform float routeWidth;uniform bool symbol;${cameraProjection}
void main(){vec4 a=project(routeStart),b=project(routeEnd);if(firstPerson){if(a.w<1.&&b.w<1.){gl_Position=vec4(2.,2.,2.,1.);return;}if(a.w<1.)a=mix(a,b,(1.-a.w)/(b.w-a.w));if(b.w<1.)b=mix(b,a,(1.-b.w)/(a.w-b.w));}vec2 delta=(b.xy/b.w-a.xy/a.w)*viewport;float size=length(delta);vec2 direction=size>.0001?delta/size:vec2(1.,0.);vec2 normal=vec2(-direction.y,direction.x);vec4 p=symbol?a:mix(a,b,corner.x);vec2 shift=symbol?(direction*corner.x+normal*corner.y)*routeWidth:(normal*corner.y*routeWidth*.5);p.xy+=shift*2./viewport*p.w;gl_Position=p;}`);
    const routeFs = shader(gl.FRAGMENT_SHADER, 'precision mediump float;uniform vec3 routeColor;void main(){gl_FragColor=vec4(routeColor,1.);}');
    this.routeProgram = gl.createProgram();
    gl.attachShader(this.routeProgram, routeVs); gl.attachShader(this.routeProgram, routeFs); gl.linkProgram(this.routeProgram);
    gl.deleteShader(routeVs); gl.deleteShader(routeFs);
    if (!gl.getProgramParameter(this.routeProgram, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(this.routeProgram));
    this.routeLocations = Object.fromEntries(['center', 'camera', 'aspect', 'firstPerson', 'eye', 'forward', 'right', 'up', 'focal', 'viewport', 'routeWidth', 'symbol', 'routeColor'].map((name) => [name, gl.getUniformLocation(this.routeProgram, name)]));
    for (const name of ['routeStart', 'routeEnd', 'corner']) this.routeLocations[name] = gl.getAttribLocation(this.routeProgram, name);
    const vertices = [];
    const { width, height, x, y, elevations } = mesh;
    this.lighting = terrainLighting(mesh);
    const hs = elevations.filter(Number.isFinite), terrainColors = this.lighting.gridColors;
    this.mean = hs.length ? hs.reduce((a, b) => a + b, 0) / hs.length : 0;
    const vertex = (i, j) => {
      const h = elevations[j * width + i];
      return !Number.isFinite(h) ? null : [x[i], y[j], h, ...terrainColors[j * width + i]];
    };
    for (let j = 0; j < height - 1; j++)
      for (let i = 0; i < width - 1; i++)
        for (const tri of [
          [vertex(i, j), vertex(i + 1, j), vertex(i, j + 1)],
          [vertex(i + 1, j), vertex(i + 1, j + 1), vertex(i, j + 1)],
        ]) {
          if (tri.some((v) => !v)) continue;
          for (const v of tri) vertices.push(...v);
        }
    this.terrain = this.makeBuffer(vertices, gl.TRIANGLES);
    for (const [key, batches] of Object.entries(scene?.render || {})) {
      const triangles = [],
        lines = [];
      for (const batch of batches) {
        const target = batch.mode === "lines" ? lines : triangles,
          positions = batch.vertices;
        for (
          let i = 0;
          i < positions.length;
          i += batch.mode === "lines" ? 6 : 9
        ) {
          const shade =
            batch.mode === "lines"
              ? 1
              : this.shade([
                  positions.slice(i, i + 3),
                  positions.slice(i + 3, i + 6),
                  positions.slice(i + 6, i + 9),
                ]);
          const count = batch.mode === "lines" ? 2 : 3;
          for (let k = 0; k < count; k++) {
            const p = positions.slice(i + k * 3, i + k * 3 + 3);
            target.push(
              ...p,
              ...(key === 'landcover' && batch.mode !== 'lines' ? this.lighting.colorsAt(p, batch.color) : batch.color.map((c) => c * shade)),
            );
          }
        }
      }
      this.groups[key] = [
        this.makeBuffer(triangles, gl.TRIANGLES),
        this.makeBuffer(lines, gl.LINES),
      ];
      this.visibility[key] = true;
    }
    this.dynamic = gl.createBuffer();
    if (typeof document !== 'undefined' && canvas.parentElement) {
      this.annotationLayer = document.createElement('div');
      this.annotationLayer.className = 'terrain-annotations';
      this.annotationLayer.setAttribute('aria-hidden', 'true');
      Object.assign(this.annotationLayer.style, { position: 'absolute', inset: '0', pointerEvents: 'none', overflow: 'hidden', zIndex: '410' });
      canvas.parentElement.append(this.annotationLayer);
    }
    const listen = (event, handler, options = {}) =>
      canvas.addEventListener(event, handler, {
        ...options,
        signal: this.events.signal,
      });
    let drag = null;
    listen("pointerdown", (e) => {
      drag = { x: e.clientX, y: e.clientY, pan: e.shiftKey || e.button === 2 };
      canvas.setPointerCapture(e.pointerId);
    });
    listen("contextmenu", (e) => e.preventDefault());
    listen("pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x,
        dy = e.clientY - drag.y;
      if (this.firstPerson) {
        this.fpvYaw -= dx * 0.005;
        this.fpvPitch = Math.max(
          -1.2,
          Math.min(0.8, this.fpvPitch + dy * 0.004),
        );
      } else if (drag.pan) {
        const scale = ((this.extent / this.zoom) * 2) / canvas.clientWidth;
        const c = Math.cos(this.yaw),
          s = Math.sin(this.yaw),
          yy = dy / Math.sin(this.pitch);
        this.center[0] -= (dx * c - yy * s) * scale;
        this.center[1] += (dx * s + yy * c) * scale;
      } else {
        this.yaw += dx * 0.006;
        this.pitch = Math.max(0.15, Math.min(1.5, this.pitch + dy * 0.005));
      }
      drag.x = e.clientX;
      drag.y = e.clientY;
      this.draw();
    });
    for (const event of ["pointerup", "pointercancel", "lostpointercapture"])
      listen(event, () => (drag = null));
    listen(
      "wheel",
      (e) => {
        e.preventDefault();
        this.zoomBy(Math.exp(-e.deltaY * 0.001));
      },
      { passive: false },
    );
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe(canvas);
    this.reset();
  }
  shade(tri) {
    const a = tri[0],
      b = tri[1],
      c = tri[2],
      u = b.map((v, i) => v - a[i]),
      v = c.map((q, i) => q - a[i]);
    const n = [
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
      ],
      d = Math.hypot(...n) || 1;
    return (
      0.68 + 0.32 * Math.abs((-0.35 * n[0] - 0.35 * n[1] + 0.87 * n[2]) / d)
    );
  }
  makeBuffer(data, mode) {
    const gl = this.gl,
      buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
    return { buffer, count: data.length / 6, mode };
  }
  deleteBuffers(buffers) {
    for (const item of buffers) {
      if (item.buffer) this.gl.deleteBuffer(item.buffer);
      if (item.colors) this.gl.deleteBuffer(item.colors);
    }
  }
  async setScene(scene, { signal } = {}) {
    const version = ++this.sceneVersion;
    this.sceneRequest?.abort();
    const request = (this.sceneRequest = new AbortController());
    if (signal?.aborted) request.abort();
    const cancel = () => request.abort();
    signal?.addEventListener("abort", cancel, { once: true });
    const assets = scene?.typed_assets;
    if (!assets || assets.schema_version !== "typed-scene-1")
      throw new Error("Contrato de escena 3D desconocido");
    if (
      assets.crs !== "EPSG:32719" ||
      assets.origin_utm.some(
        (v, i) => Math.abs(v - this.mesh.origin_utm[i]) > 0.01,
      )
    )
      throw new Error("Origen o CRS incompatible en escena 3D");
    const prepared = {};
    let totalBytes = 0;
    const read = async (spec, count, dtype) => {
      if (spec.dtype !== dtype || spec.components !== 3)
        throw new Error("Buffer 3D incompatible");
      const url = new URL(spec.url, location.href);
      if (url.origin !== location.origin)
        throw new Error("Recurso 3D fuera del servidor");
      const response = await fetch(url, { signal: request.signal });
      if (!response.ok) throw new Error("No se pudo cargar el recurso 3D");
      const bytes = await response.arrayBuffer();
      const expected = count * 3 * (dtype === "float32-le" ? 4 : 1);
      totalBytes += bytes.byteLength;
      if (bytes.byteLength !== expected || totalBytes > 256 * 1024 * 1024)
        throw new Error("Tamaño de escena 3D inválido");
      const digest = Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
        (v) => v.toString(16).padStart(2, "0"),
      ).join("");
      if (digest !== spec.sha256)
        throw new Error("Integridad del recurso 3D inválida");
      return bytes;
    };
    try {
      // Sequential groups bound transient memory; only immutable assets use browser caching.
      for (const [key, batches] of Object.entries(assets.groups)) {
        prepared[key] = [];
        for (const batch of batches) {
          if (
            !Number.isSafeInteger(batch.count) ||
            batch.count < 0 ||
            batch.count > 15000000 ||
            !["lines", "triangles"].includes(batch.mode)
          )
            throw new Error("Conteo 3D inválido");
          const [positions, colors] = await Promise.all([
            read(batch.positions, batch.count, "float32-le"),
            read(batch.colors, batch.count, "uint8"),
          ]);
          if (
            request.signal.aborted ||
            this.disposed ||
            version !== this.sceneVersion
          )
            throw new DOMException("Escena reemplazada", "AbortError");
          const gl = this.gl,
            buffer = gl.createBuffer(),
            colorBuffer = gl.createBuffer();
          gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
          gl.bufferData(
            gl.ARRAY_BUFFER,
            new Float32Array(positions),
            gl.STATIC_DRAW,
          );
          gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer);
          gl.bufferData(
            gl.ARRAY_BUFFER,
            new Uint8Array(colors),
            gl.STATIC_DRAW,
          );
          prepared[key].push({
            buffer,
            colors: colorBuffer,
            count: batch.count,
            mode: batch.mode === "lines" ? gl.LINES : gl.TRIANGLES,
          });
        }
      }
      if (
        request.signal.aborted ||
        this.disposed ||
        version !== this.sceneVersion
      )
        throw new DOMException("Escena reemplazada", "AbortError");
      for (const buffers of Object.values(this.groups))
        this.deleteBuffers(buffers);
      this.groups = prepared;
      this.scene = { sha256: scene.sha256, commune_id: scene.commune_id };
      for (const key of Object.keys(prepared))
        if (!(key in this.visibility)) this.visibility[key] = true;
      this.draw();
    } catch (error) {
      for (const buffers of Object.values(prepared))
        this.deleteBuffers(buffers);
      throw error;
    } finally {
      signal?.removeEventListener("abort", cancel);
    }
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    ++this.sceneVersion;
    this.sceneRequest?.abort();
    this.events.abort();
    this.observer?.disconnect();
    this.deleteBuffers([this.terrain, ...this.routeBuffers, ...this.forbiddenZoneBuffers]);
    this.forbiddenZoneBuffers = [];
    for (const buffers of Object.values(this.groups))
      this.deleteBuffers(buffers);
    this.gl.deleteBuffer(this.dynamic);
    this.gl.deleteProgram(this.program);
    this.gl.deleteProgram(this.routeProgram);
    this.annotationLayer?.remove();
    this.annotationNodes.clear();
    this.groups = {};
    this.routeBuffers = [];
    this.lines = [];
    this.flightPose = null;
    this.marker = null;
  }
  reset() {
    const m = this.mesh;
    this.center = [m.x.at(-1) / 2, m.y.at(-1) / 2, this.mean];
    this.extent = Math.max(m.x.at(-1), m.y.at(-1));
    this.zoom = 1.6;
    this.focused = false;
    this.draw();
  }
  focusRoutes() {
    const points = this.lines
      .filter((l) => !l.point && !l.target)
      .flatMap((l) => l.points);
    if (!points.length) return;
    const ox = this.mesh.origin_utm[0],
      oy = this.mesh.origin_utm[1];
    let minx = Infinity,
      maxx = -Infinity,
      miny = Infinity,
      maxy = -Infinity,
      z = 0;
    for (const p of points) {
      minx = Math.min(minx, p[0] - ox);
      maxx = Math.max(maxx, p[0] - ox);
      miny = Math.min(miny, p[1] - oy);
      maxy = Math.max(maxy, p[1] - oy);
      z += p[2];
    }
    this.center = [
      (minx + maxx) / 2,
      (miny + maxy) / 2,
      z / points.length - 40,
    ];
    this.extent = Math.max(600, maxx - minx + 300, maxy - miny + 300);
    this.zoom = 1.5;
    this.focused = true;
    this.draw();
  }
  setRoutes(lines) {
    if (this.disposed) return;
    this.deleteBuffers(this.routeBuffers);
    const m = this.mesh,
      gl = this.gl;
    this.routeBuffers = lines.flatMap((line) => {
      const data = [];
      const add = (p) => {
        if (p.every(Number.isFinite))
          data.push(
            p[0] - m.origin_utm[0],
            p[1] - m.origin_utm[1],
            p[2] + 2,
            ...line.color,
          );
      };
      if (line.point) {
        line.points.forEach(add);
        return [{ ...this.makeBuffer(data, gl.POINTS), target: line.target, point: true }];
      }
      const local = (p) => [p[0] - m.origin_utm[0], p[1] - m.origin_utm[1], p[2]];
      const push = (a, b, corners, target) => {
        for (const corner of corners) target.push(...local(a), ...local(b), ...corner);
      };
      for (let i = 1; i < line.points.length; i++) {
        const a = line.points[i - 1], b = line.points[i];
        if (a.every(Number.isFinite) && b.every(Number.isFinite) && Math.hypot(...b.map((n, k) => n - a[k])) > .001)
          push(a, b, [[0, -1], [0, 1], [1, -1], [1, -1], [0, 1], [1, 1]], data);
      }
      const make = (values, symbol = false) => {
        const buffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(values), gl.STATIC_DRAW);
        return { buffer, count: values.length / 8, mode: gl.TRIANGLES, screenRoute: true, symbol,
          color: line.color, widthPx: line.width_px || (line.target ? 3 : (line.selected ?? line.width >= 4) ? 6 : 3), target: line.target, key: line.key };
      };
      const items = [make(data)];
      if (!line.target && line.arrows !== false) {
        const arrows = [];
        for (const { position, ahead } of routeArrowAnchors(line.points))
          push(position, ahead, [[7, 0], [-5, -4], [-5, 4]], arrows);
        if (arrows.length) items.push(make(arrows, true));
      }
      return items;
    });
    this.canvas.dataset.routeArrows = String(this.routeBuffers.filter((item) => item.symbol).reduce((n, item) => n + item.count / 3, 0));
    this.lines = lines;
    if (!this.focused && lines.some((l) => !l.point)) this.focusRoutes();
    else this.draw();
  }
  setLayer(key, visible) {
    if (this.visibility[key] === visible) return;
    this.visibility[key] = visible;
    this.draw();
  }
  setMarker(position) {
    this.marker = position;
    if (!position) this.flightPose = null;
    this.reconcileAnnotations();
    this.draw();
  }
  zoomBy(factor) {
    if (this.disposed || !Number.isFinite(factor) || factor <= 0) return;
    if (this.firstPerson) {
      this.fov = Math.max(40, Math.min(100, this.fov / factor));
      this.fpvDistance = Math.max(18, Math.min(165, (this.fpvDistance || 58) / factor));
    }
    else this.zoom = Math.max(.3, Math.min(60, this.zoom * factor));
    this.draw();
  }
  setFire(posUtm) {
    if (this.disposed) return;
    this.fireUtm = posUtm ? [...posUtm] : null;
    this.draw();
  }
  setDroneNote(note) {
    if (this.disposed) return;
    const next = String(note || "");
    if (this.droneNote === next) return;
    this.droneNote = next;
    this.reconcileAnnotations();
  }
  setForbiddenZones(zones) {
    if (this.disposed) return;
    this.deleteBuffers(this.forbiddenZoneBuffers);
    this.forbiddenZoneBuffers = [];
    const m = this.mesh, gl = this.gl;
    if (!m || !zones?.length) {
      this.draw();
      return;
    }
    const ox = m.origin_utm[0], oy = m.origin_utm[1];
    const wallTris = [], topLines = [], baseLines = [];
    const pushV = (arr, pt, col) => arr.push(pt[0], pt[1], pt[2], col[0], col[1], col[2]);
    const pushTri = (arr, p1, p2, p3, col) => { pushV(arr, p1, col); pushV(arr, p2, col); pushV(arr, p3, col); };
    const pushLine = (arr, p1, p2, col) => { pushV(arr, p1, col); pushV(arr, p2, col); };
    for (const z of zones) {
      const col = z.color || [0.85, 0.16, 0.14];
      const wallH = Number.isFinite(z.heightM) ? z.heightM : 45;
      for (const ring of z.rings || []) {
        if (!ring || ring.length < 3) continue;
        const pts = ring.map(([x, y]) => {
          const g = this.sampleElevation(x, y);
          return [x - ox, y - oy, g];
        });
        for (let i = 0; i < pts.length - 1; i++) {
          const a = pts[i], b = pts[i + 1];
          const a0 = [a[0], a[1], a[2] + 2.5], b0 = [b[0], b[1], b[2] + 2.5];
          const a1 = [a[0], a[1], a[2] + wallH], b1 = [b[0], b[1], b[2] + wallH];
          pushTri(wallTris, a0, b0, b1, col);
          pushTri(wallTris, a0, b1, a1, col);
          pushLine(baseLines, a0, b0, col);
          pushLine(topLines, a1, b1, col);
        }
        // Cross-hatch diagonals across bounding/ring vertices for 3D area fill legibility
        if (pts.length >= 4) {
          const step = Math.max(1, Math.floor(pts.length / 8));
          for (let i = 0; i < Math.floor(pts.length / 2); i += step) {
            const pA = pts[i], pB = pts[(i + Math.floor(pts.length / 2)) % (pts.length - 1)];
            if (pA && pB) pushLine(baseLines, [pA[0], pA[1], pA[2] + 3.0], [pB[0], pB[1], pB[2] + 3.0], col);
          }
        }
      }
    }
    if (wallTris.length) this.forbiddenZoneBuffers.push({ ...this.makeBuffer(wallTris, gl.TRIANGLES), opacity: 0.24 });
    if (topLines.length) this.forbiddenZoneBuffers.push({ ...this.makeBuffer(topLines, gl.LINES), opacity: 0.92 });
    if (baseLines.length) this.forbiddenZoneBuffers.push({ ...this.makeBuffer(baseLines, gl.LINES), opacity: 0.85 });
    this.draw();
  }
  setAnnotations(items) {
    if (this.disposed) return;
    this.annotations = (items || []).filter((item) => annotationPaths[item.kind] && item.position_utm?.length === 3 && item.position_utm.every(Number.isFinite))
      .map((item, index) => ({ ...item, id: String(item.id ?? `${item.kind}:${index}`), label: String(item.label ?? ''), position_utm: [...item.position_utm] }));
    this.reconcileAnnotations();
    this.draw();
  }
  annotationItems() {
    const items = this.annotations;
    if (!this.marker) return items;
    return [...items.filter((item) => item.kind !== 'drone'), { id: '__flight_drone', kind: 'drone', position_utm: this.marker, label: 'Dron', note: this.droneNote || '', selected: true }];
  }
  reconcileAnnotations() {
    if (!this.annotationLayer) return;
    const wanted = new Set();
    for (const item of this.annotationItems()) {
      wanted.add(item.id);
      let node = this.annotationNodes.get(item.id);
      if (!node) {
        const element = document.createElement('div'), note = document.createElement('span'), icon = document.createElement('span'), label = document.createElement('span');
        note.className = 'terrain-annotation-note';
        Object.assign(note.style, { maxWidth: '280px', background: '#fff7ed', color: '#9a3412', border: '1px solid rgba(234,88,12,0.45)', borderRadius: '6px', padding: '3px 7px', font: '600 11px/1.25 system-ui,sans-serif', boxShadow: '0 2px 6px rgba(0,0,0,0.16)', textAlign: 'center', whiteSpace: 'normal' });
        note.hidden = true;
        element.className = 'terrain-annotation'; icon.className = 'terrain-annotation-icon'; label.className = 'terrain-annotation-label';
        Object.assign(element.style, { position: 'absolute', top: '0', left: '0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '3px', pointerEvents: 'none', willChange: 'transform' });
        Object.assign(icon.style, { display: 'block', width: item.kind === 'drone' ? '36px' : '28px', height: item.kind === 'drone' ? '36px' : '28px', filter: 'drop-shadow(0 1px 2px #ffffff) drop-shadow(0 0 2px #ffffff)' });
        Object.assign(label.style, { maxWidth: '230px', background: '#ffffffeb', color: '#173d33', borderRadius: '3px', padding: '2px 5px', font: '600 11px system-ui,sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' });
        element.append(note, icon, label); this.annotationLayer.append(element);
        node = { element, note, icon, label }; this.annotationNodes.set(item.id, node);
      }
      const color = item.kind === 'fire' || item.kind === 'threat' ? '#b74720' : item.kind === 'station' ? '#b91c1c' : item.kind === 'drone' ? '#a73d18' : '#1a5941';
      node.element.dataset.kind = item.kind; node.element.dataset.selected = String(!!item.selected);
      node.icon.style.color = color;
      if (node.kind !== item.kind) {
        node.icon.innerHTML = `<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${annotationPaths[item.kind]}</svg>`;
        node.kind = item.kind;
      }
      if (node.note) {
        if (node.note.textContent !== (item.note || '')) node.note.textContent = item.note || '';
        node.note.hidden = !item.note;
      }
      if (node.label.textContent !== (item.label || '')) node.label.textContent = item.label || '';
      node.label.hidden = !item.label;
      node.element.title = item.label || item.kind;
    }
    for (const [id, node] of this.annotationNodes) if (!wanted.has(id)) { node.element.remove(); this.annotationNodes.delete(id); }
  }
  updateAnnotations(camera) {
    if (!this.annotationLayer) return;
    this.annotationLayer.hidden = this.canvas.hidden;
    let visible = 0;
    const rectangles = [], baseIcons = [], canvasRect = this.canvas.getBoundingClientRect?.() || { left: 0, top: 0 };
    const priority = (item) => item.kind === 'drone' ? 3 : item.kind === 'base' && item.selected ? 2 : item.kind === 'base' ? 1 : 0;
    const overlap = (a, b) => a.left < b.right + 5 && a.right + 5 > b.left && a.top < b.bottom + 4 && a.bottom + 4 > b.top;
    const items = [...this.annotationItems()].sort((a, b) => priority(b) - priority(a));
    for (const item of items) {
      const node = this.annotationNodes.get(item.id);
      if (!node) continue;
      const point = projectTerrainPoint(item.position_utm, camera);
      node.element.hidden = !point.visible || !!(camera.fpv && item.kind === 'drone');
      // The inline display must not override the HTML hidden attribute.
      node.element.style.display = node.element.hidden ? 'none' : 'flex';
      if (node.element.hidden) continue;
      visible++;
      const matchingBase = item.kind === 'station' && baseIcons.find((base) => Math.hypot(base.x - point.x, base.y - point.y) < 18);
      if (matchingBase) { point.x = Math.max(12, Math.min(camera.width - 12, matchingBase.x + 19)); point.y = Math.max(12, Math.min(camera.height - 12, matchingBase.y - 13)); }
      if (item.kind === 'base') baseIcons.push({ x: point.x, y: point.y });
      const iconSize = item.kind === 'drone' ? 36 : matchingBase ? 20 : 28, selectedBase = item.kind === 'base' && item.selected;
      node.element.dataset.badge = String(!!matchingBase);
      node.icon.style.width = node.icon.style.height = `${iconSize}px`;
      node.element.style.transform = `translate(${point.x.toFixed(2)}px,${point.y.toFixed(2)}px) translate(-50%,-${iconSize / 2}px)`;
      if (item.kind === 'drone') {
        let ahead = this.flightPose?.ahead;
        if (!ahead && Number.isFinite(item.heading_deg)) { const a = item.heading_deg * Math.PI / 180; ahead = [item.position_utm[0] + Math.sin(a) * 10, item.position_utm[1] + Math.cos(a) * 10, item.position_utm[2]]; }
        const next = ahead && projectTerrainPoint(ahead, camera);
        const angle = next && Number.isFinite(next.x + next.y) ? Math.atan2(next.x - point.x, point.y - next.y) * 180 / Math.PI : 0;
        node.icon.style.transform = `rotate(${angle.toFixed(2)}deg)`;
      }
      node.label.hidden = !item.label;
      node.label.style.transform = '';
      const maxWidth = Math.max(80, Math.min(selectedBase ? 280 : 230, camera.width - 24));
      Object.assign(node.label.style, { maxWidth: `${maxWidth}px`, whiteSpace: selectedBase ? 'normal' : 'nowrap',
        textOverflow: selectedBase ? 'clip' : 'ellipsis', overflowWrap: selectedBase ? 'anywhere' : 'normal' });
      if (item.label) {
        const measured = node.label.getBoundingClientRect?.();
        const textWidth = Math.min(maxWidth, item.label.length * 6.8 + 10), textHeight = selectedBase ? Math.ceil((item.label.length * 6.8 + 10) / maxWidth) * 15 + 4 : 19;
        const rect = measured?.width ? { left: measured.left - canvasRect.left, top: measured.top - canvasRect.top, width: measured.width, height: measured.height }
          : { left: point.x - textWidth / 2, top: point.y + iconSize / 2 + 3, width: textWidth, height: textHeight };
        const shifts = priority(item) >= 2 ? [[0, 0], [0, -rect.height - iconSize - 8], [rect.width / 2 + 22, 0], [-rect.width / 2 - 22, 0], [0, rect.height + 8]] : [[0, 0]];
        let chosen = null;
        for (const [x, y] of shifts) {
          const left = Math.max(8, Math.min(camera.width - rect.width - 8, rect.left + x));
          const top = Math.max(8, Math.min(camera.height - rect.height - 8, rect.top + y));
          const candidate = { left, top, right: left + rect.width, bottom: top + rect.height };
          if (!rectangles.some((other) => overlap(candidate, other))) { chosen = candidate; break; }
        }
        if (!chosen && priority(item) < 2) node.label.hidden = true;
        else {
          chosen ||= { left: rect.left, top: rect.top, right: rect.left + rect.width, bottom: rect.top + rect.height };
          node.label.style.transform = `translate(${(chosen.left - rect.left).toFixed(2)}px,${(chosen.top - rect.top).toFixed(2)}px)`;
          rectangles.push(chosen);
        }
      }
      node.element.dataset.labelVisible = String(!node.label.hidden);
    }
    this.canvas.dataset.annotationCount = String(visible);
  }
  focusPoints(points, kind = "target") {
    if (!points.length) return;
    this.firstPerson = false;
    const xs = points.map((p) => p[0] - this.mesh.origin_utm[0]),
      ys = points.map((p) => p[1] - this.mesh.origin_utm[1]);
    this.center = [
      (Math.min(...xs) + Math.max(...xs)) / 2,
      (Math.min(...ys) + Math.max(...ys)) / 2,
      points.reduce((s, p) => s + p[2], 0) / points.length,
    ];
    this.extent = Math.max(
      350,
      Math.max(...xs) - Math.min(...xs) + 200,
      Math.max(...ys) - Math.min(...ys) + 200,
    );
    this.zoom = 1.4;
    this.focused = true;
    this.canvas.dataset.focus = kind;
    this.draw();
  }
  setFirstPerson(enabled) {
    this.firstPerson = !!enabled;
    if (enabled) {
      this.fpvYaw = 0;
      this.fpvPitch = -0.32;
    this.fpvDistance = 58;
    this.swathM = 200;
    }
    this.draw();
  }
  setFlightPose(position, ahead, follow = false) {
    this.marker = position;
    this.flightPose = { position, ahead };
    if (!this.annotationNodes.has('__flight_drone')) this.reconcileAnnotations();
    if (follow && !this.firstPerson)
      this.center = [
        position[0] - this.mesh.origin_utm[0],
        position[1] - this.mesh.origin_utm[1],
        position[2] - 35,
      ];
    this.draw();
  }
  bind(buffer) {
    const gl = this.gl;
    for (const name of ['routeStart', 'routeEnd', 'corner']) {
      const i = this.routeLocations[name];
      if (i !== this.locations.position && i !== this.locations.color) gl.disableVertexAttribArray(i);
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    for (const [name, offset] of [
      ["position", 0],
      ["color", 12],
    ]) {
      const i = this.locations[name];
      gl.enableVertexAttribArray(i);
      gl.vertexAttribPointer(i, 3, gl.FLOAT, false, 24, offset);
    }
  }
  bindItem(item) {
    if (!item.colors) {
      this.bind(item.buffer);
      return;
    }
    const gl = this.gl;
    for (const name of ['routeStart', 'routeEnd', 'corner']) {
      const i = this.routeLocations[name];
      if (i !== this.locations.position && i !== this.locations.color) gl.disableVertexAttribArray(i);
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, item.buffer);
    gl.enableVertexAttribArray(this.locations.position);
    gl.vertexAttribPointer(this.locations.position, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, item.colors);
    gl.enableVertexAttribArray(this.locations.color);
    gl.vertexAttribPointer(
      this.locations.color,
      3,
      gl.UNSIGNED_BYTE,
      true,
      0,
      0,
    );
  }
  setSwath(swathM) {
    if (Number.isFinite(swathM) && swathM > 10) this.swathM = swathM;
  }
  setThermalContext(ctx) {
    this.thermalCtx = ctx || null;
  }
  setCoverageTrail(trailPoints, plannedPoints = undefined) {
    this.coverageTrail = Array.isArray(trailPoints) ? trailPoints : [];
    if (plannedPoints !== undefined) {
      this.plannedCorridor = Array.isArray(plannedPoints) ? plannedPoints : [];
    }
    this.draw();
  }
  buildTerrainCorridor(pts, halfW, colFill, colEdge, zLift = 1.9) {
    const tris = [], lines = [];
    if (!pts || pts.length < 2) return { tris, lines };
    const m = this.mesh, ox = m.origin_utm[0], oy = m.origin_utm[1];
    const samples = [pts[0]];
    const stepM = 135;
    for (let i = 1; i < pts.length; i++) {
      const a = samples[samples.length - 1], b = pts[i];
      if (!a || !b || !Number.isFinite(b[0]) || !Number.isFinite(b[1])) continue;
      const dist = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (dist < 28 && i < pts.length - 1) continue;
      if (dist > stepM) {
        const nSteps = Math.min(14, Math.ceil(dist / stepM));
        for (let s = 1; s <= nSteps; s++) {
          const f = s / nSteps;
          samples.push([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]);
        }
      } else {
        samples.push([b[0], b[1]]);
      }
    }
    if (samples.length < 2) return { tris, lines };
    const COLS = 4;
    const rows = [];
    for (let i = 0; i < samples.length; i++) {
      const p = samples[i];
      const prev = samples[Math.max(0, i - 1)];
      const next = samples[Math.min(samples.length - 1, i + 1)];
      let dx = next[0] - prev[0], dy = next[1] - prev[1];
      const len = Math.hypot(dx, dy) || 1;
      dx /= len; dy /= len;
      const rx = dy, ry = -dx;
      const row = [];
      for (let c = 0; c <= COLS; c++) {
        const u = -halfW + (2 * halfW * c) / COLS;
        const wx = p[0] + rx * u, wy = p[1] + ry * u;
        const wz = this.sampleElevation(wx, wy) + zLift;
        row.push([wx - ox, wy - oy, wz]);
      }
      rows.push(row);
    }
    const pushV = (arr, pt, col) => arr.push(pt[0], pt[1], pt[2], col[0], col[1], col[2]);
    const pushTri = (arr, p1, p2, p3, col) => { pushV(arr, p1, col); pushV(arr, p2, col); pushV(arr, p3, col); };
    const pushLine = (arr, p1, p2, col) => { pushV(arr, p1, col); pushV(arr, p2, col); };
    for (let r = 0; r < rows.length - 1; r++) {
      for (let c = 0; c < COLS; c++) {
        pushTri(tris, rows[r][c], rows[r + 1][c], rows[r + 1][c + 1], colFill);
        pushTri(tris, rows[r][c], rows[r + 1][c + 1], rows[r][c + 1], colFill);
      }
      pushLine(lines, rows[r][0], rows[r + 1][0], colEdge);
      pushLine(lines, rows[r][COLS], rows[r + 1][COLS], colEdge);
      if (r % 2 === 0) {
        for (let c = 0; c < COLS; c++) pushLine(lines, rows[r][c], rows[r][c + 1], colEdge);
      }
    }
    return { tris, lines };
  }
  sampleElevation(xUtm, yUtm) {
    const m = this.mesh;
    if (!m || m.width < 2 || m.height < 2) return this.mean || 0;
    const dx = (m.x[1] - m.x[0]) || 1, dy = (m.y[1] - m.y[0]) || 1;
    const fx = Math.max(0, Math.min(m.width - 1.001, (xUtm - m.origin_utm[0]) / dx));
    const fy = Math.max(0, Math.min(m.height - 1.001, (yUtm - m.origin_utm[1]) / dy));
    const ix = Math.floor(fx), iy = Math.floor(fy), tx = fx - ix, ty = fy - iy;
    const idx = iy * m.width + ix;
    const h00 = m.elevations[idx], h10 = m.elevations[idx + 1], h01 = m.elevations[idx + m.width], h11 = m.elevations[idx + m.width + 1];
    if (![h00, h10, h01, h11].every(Number.isFinite)) return Number.isFinite(h00) ? h00 : (this.mean || 0);
    return (1 - tx) * (1 - ty) * h00 + tx * (1 - ty) * h10 + (1 - tx) * ty * h01 + tx * ty * h11;
  }
  drawDroneVision(camera) {
    const gl = this.gl, m = this.mesh;
    const swath = Math.max(60, Math.min(420, this.swathM || 200));
    const halfW = swath * 0.5;
    gl.useProgram(this.program);
    this.applyCamera(this.locations, camera);
    this.bind(this.dynamic);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);

    if (this.plannedCorridor?.length >= 2) {
      const planned = this.buildTerrainCorridor(
        this.plannedCorridor,
        halfW,
        [0.06, 0.78, 0.54],
        [0.14, 0.88, 0.66],
        1.5,
      );
      if (planned.tris.length) {
        gl.uniform1f(this.locations.opacity, this.flightPose ? 0.12 : 0.22);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(planned.tris), gl.DYNAMIC_DRAW);
        gl.drawArrays(gl.TRIANGLES, 0, planned.tris.length / 6);
      }
      if (planned.lines.length) {
        gl.uniform1f(this.locations.opacity, this.flightPose ? 0.32 : 0.55);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(planned.lines), gl.DYNAMIC_DRAW);
        gl.drawArrays(gl.LINES, 0, planned.lines.length / 6);
      }
    }

    if (this.coverageTrail?.length >= 2) {
      const swept = this.buildTerrainCorridor(
        this.coverageTrail,
        halfW,
        [0.02, 0.94, 0.76],
        [0.25, 1.0, 0.88],
        2.0,
      );
      if (swept.tris.length) {
        gl.uniform1f(this.locations.opacity, 0.34);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(swept.tris), gl.DYNAMIC_DRAW);
        gl.drawArrays(gl.TRIANGLES, 0, swept.tris.length / 6);
      }
      if (swept.lines.length) {
        gl.uniform1f(this.locations.opacity, 0.76);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(swept.lines), gl.DYNAMIC_DRAW);
        gl.drawArrays(gl.LINES, 0, swept.lines.length / 6);
      }
    }

    if (!this.flightPose) {
      gl.depthMask(true);
      gl.disable(gl.BLEND);
      return;
    }
    const { position: p, ahead: a } = this.flightPose;
    if (!p || !a || !p.every(Number.isFinite)) return;
    const ox = m.origin_utm[0], oy = m.origin_utm[1];
    const heading = Math.atan2(a[1] - p[1], a[0] - p[0]);
    const fx = Math.cos(heading), fy = Math.sin(heading);
    const rx = Math.sin(heading), ry = -Math.cos(heading);
    const dx = p[0] - ox, dy = p[1] - oy, dz = p[2];
    const apex = [dx + fx * 1.1, dy + fy * 1.1, dz - 1.0];
    const vMin = -35, vMax = 145;
    const ROWS = 10, COLS = 10;
    const grid = [];
    for (let r = 0; r <= ROWS; r++) {
      const row = [];
      const v = vMin + (vMax - vMin) * (r / ROWS);
      for (let c = 0; c <= COLS; c++) {
        const u = -halfW + swath * (c / COLS);
        const wx = p[0] + fx * v + rx * u;
        const wy = p[1] + fy * v + ry * u;
        const wz = Math.min(dz - 4, this.sampleElevation(wx, wy) + 2.2);
        row.push([wx - ox, wy - oy, wz]);
      }
      grid.push(row);
    }
    const pushV = (arr, pt, col) => arr.push(pt[0], pt[1], pt[2], col[0], col[1], col[2]);
    const pushTri = (arr, p1, p2, p3, col) => { pushV(arr, p1, col); pushV(arr, p2, col); pushV(arr, p3, col); };
    const pushLine = (arr, p1, p2, col) => { pushV(arr, p1, col); pushV(arr, p2, col); };

    const groundTris = [];
    const tCtx = this.thermalCtx || {};
    const animSec = performance.now() * 0.001 + (tCtx.timeS || 0) * 0.18;
    const scanColF = ((Math.sin(animSec * 3.2) + 1) * 0.5) * COLS;
    const scanRowF = ((Math.cos(animSec * 2.1) + 1) * 0.5) * (ROWS - 1);
    const scanColIdx = Math.min(COLS - 1, Math.max(0, Math.floor(scanColF)));
    const scanRowIdx = Math.min(ROWS - 1, Math.max(0, Math.floor(scanRowF)));
    const fireUtm = tCtx.fireUtm;
    const threatsUtm = tCtx.threatsUtm || [];
    const isFireLock = Boolean(
      tCtx.phase === "detection" ||
      tCtx.phase === "report" ||
      (fireUtm && Math.hypot(fireUtm[0] - p[0], fireUtm[1] - p[1]) <= swath * 0.85),
    );

    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const isFront = r === ROWS - 1;
        const cellCenter = [
          (grid[r][c][0] + grid[r + 1][c + 1][0]) * 0.5 + ox,
          (grid[r][c][1] + grid[r + 1][c + 1][1]) * 0.5 + oy,
        ];
        const distScan = Math.hypot(c - scanColF + 0.5, (r - scanRowF + 0.5) * 0.65);
        const nearThreat = threatsUtm.some(
          (th) => Math.hypot(th[0] - cellCenter[0], th[1] - cellCenter[1]) < 140,
        );
        const nearFire =
          fireUtm && Math.hypot(fireUtm[0] - cellCenter[0], fireUtm[1] - cellCenter[1]) < 95;
        let col;
        if (nearFire) {
          col = [1.0, 0.22, 0.05];
        } else if (distScan < 1.35) {
          col = nearThreat ? [1.0, 0.36, 0.08] : [1.0, 0.68, 0.14];
        } else if (c === scanColIdx) {
          col = [0.95, 0.82, 0.22];
        } else if (nearThreat) {
          col = [0.92, 0.48, 0.16];
        } else {
          col = isFront
            ? [0.18, 1.0, 0.90]
            : (r + c) % 2 === 0
              ? [0.0, 0.92, 0.78]
              : [0.04, 0.78, 0.70];
        }
        pushTri(groundTris, grid[r][c], grid[r + 1][c], grid[r + 1][c + 1], col);
        pushTri(groundTris, grid[r][c], grid[r + 1][c + 1], grid[r][c + 1], col);
      }
    }

    const coneTris = [];
    const coneCol = isFireLock ? [1.0, 0.35, 0.08] : [0.02, 0.88, 0.84];
    for (let c = 0; c < COLS; c++) {
      pushTri(coneTris, apex, grid[ROWS][c], grid[ROWS][c + 1], coneCol);
      pushTri(coneTris, apex, grid[0][c + 1], grid[0][c], coneCol);
    }
    for (let r = 0; r < ROWS; r++) {
      pushTri(coneTris, apex, grid[r][0], grid[r + 1][0], coneCol);
      pushTri(coneTris, apex, grid[r + 1][COLS], grid[r][COLS], coneCol);
    }
    // Active thermal scan curtain inside the cone (sondeo IR en busca de foco)
    const scanColClamped = Math.min(COLS, Math.max(0, Math.round(scanColF)));
    const scanCurtainCol = isFireLock ? [1.0, 0.25, 0.05] : [1.0, 0.65, 0.12];
    for (let r = 0; r < ROWS; r++) {
      pushTri(coneTris, apex, grid[r][scanColClamped], grid[r + 1][scanColClamped], scanCurtainCol);
    }

    const gridLines = [];
    const lineCol = [0.06, 0.98, 0.86];
    const borderCol = [0.48, 1.0, 0.96];
    for (let r = 0; r <= ROWS; r++) {
      const col = r === 0 || r === ROWS ? borderCol : lineCol;
      for (let c = 0; c < COLS; c++) pushLine(gridLines, grid[r][c], grid[r][c + 1], col);
    }
    for (let c = 0; c <= COLS; c++) {
      const col =
        c === scanColClamped
          ? [1.0, 0.72, 0.16]
          : c === 0 || c === COLS
            ? borderCol
            : lineCol;
      for (let r = 0; r < ROWS; r++) pushLine(gridLines, grid[r][c], grid[r + 1][c], col);
    }
    const rayCol = [0.16, 0.96, 0.90];
    const midR = Math.floor(ROWS / 2), midC = Math.floor(COLS / 2);
    for (const corner of [
      grid[0][0], grid[0][COLS], grid[ROWS][0], grid[ROWS][COLS],
      grid[ROWS][midC], grid[0][midC], grid[midR][0], grid[midR][COLS],
    ]) {
      pushLine(gridLines, apex, corner, rayCol);
    }
    // Thermal probe laser & reticle on the ground (sondeo activo de focos)
    let probeTarget;
    if (isFireLock && fireUtm) {
      const fz = this.sampleElevation(fireUtm[0], fireUtm[1]) + 2.6;
      probeTarget = [fireUtm[0] - ox, fireUtm[1] - oy, fz];
    } else {
      const pr = grid[scanRowIdx][scanColIdx];
      const pr2 = grid[scanRowIdx + 1][scanColIdx + 1];
      probeTarget = [
        (pr[0] + pr2[0]) * 0.5,
        (pr[1] + pr2[1]) * 0.5,
        (pr[2] + pr2[2]) * 0.5 + 0.6,
      ];
    }
    const probeCol = isFireLock ? [1.0, 0.18, 0.04] : [1.0, 0.74, 0.14];
    pushLine(gridLines, apex, probeTarget, probeCol);
    pushLine(gridLines, grid[0][scanColClamped], grid[ROWS][scanColClamped], probeCol);
    const ringRadii = isFireLock ? [14, 28, 44] : [12, 24];
    const ringSegs = 12;
    for (const rad of ringRadii) {
      for (let s = 0; s < ringSegs; s++) {
        const a0 = (s / ringSegs) * Math.PI * 2;
        const a1 = ((s + 1) / ringSegs) * Math.PI * 2;
        const p0 = [
          probeTarget[0] + Math.cos(a0) * rad,
          probeTarget[1] + Math.sin(a0) * rad,
          probeTarget[2] + 0.5,
        ];
        const p1 = [
          probeTarget[0] + Math.cos(a1) * rad,
          probeTarget[1] + Math.sin(a1) * rad,
          probeTarget[2] + 0.5,
        ];
        pushLine(gridLines, p0, p1, probeCol);
      }
    }

    // 3D Quadcopter Drone Mesh at (dx, dy, dz)
    const droneTris = [], droneLines = [];
    const localPt = (f, r, u) => [dx + fx * f + rx * r, dy + fy * f + ry * r, dz + u];
    const bodyCol = [0.15, 0.20, 0.24], topCol = [0.24, 0.30, 0.35], gimbalCol = [0.88, 0.22, 0.52];
    const nose = localPt(3.4, 0, 0.2), tail = localPt(-3.2, 0, 0.2);
    const leftB = localPt(0, -1.6, 0.2), rightB = localPt(0, 1.6, 0.2);
    const topB = localPt(0.2, 0, 1.15), botB = localPt(0.4, 0, -1.05);
    pushTri(droneTris, topB, nose, rightB, topCol);
    pushTri(droneTris, topB, rightB, tail, bodyCol);
    pushTri(droneTris, topB, tail, leftB, bodyCol);
    pushTri(droneTris, topB, leftB, nose, topCol);
    pushTri(droneTris, botB, rightB, nose, gimbalCol);
    pushTri(droneTris, botB, tail, rightB, bodyCol);
    pushTri(droneTris, botB, leftB, tail, bodyCol);
    pushTri(droneTris, botB, nose, leftB, gimbalCol);

    const armCoords = [[4.2, 4.6], [4.2, -4.6], [-4.0, 4.6], [-4.0, -4.6]];
    const armCol = [0.10, 0.14, 0.18], rotorCol = [0.12, 0.96, 0.88];
    for (const [af, ar] of armCoords) {
      const hub = localPt(af, ar, 0.35);
      pushLine(droneLines, localPt(af * 0.2, ar * 0.2, 0.2), hub, armCol);
      pushLine(droneLines, localPt(af, ar, -1.2), hub, armCol);
      const R = 2.4, segs = 10;
      for (let s = 0; s < segs; s++) {
        const a0 = (s / segs) * Math.PI * 2, a1 = ((s + 1) / segs) * Math.PI * 2;
        const p0 = localPt(af + Math.cos(a0) * R, ar + Math.sin(a0) * R, 0.5);
        const p1 = localPt(af + Math.cos(a1) * R, ar + Math.sin(a1) * R, 0.5);
        pushLine(droneLines, p0, p1, rotorCol);
        pushTri(droneTris, hub, p0, p1, [0.06, 0.85, 0.78]);
      }
    }

    gl.useProgram(this.program);
    this.applyCamera(this.locations, camera);
    this.bind(this.dynamic);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);

    if (groundTris.length) {
      gl.uniform1f(this.locations.opacity, 0.28);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(groundTris), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.TRIANGLES, 0, groundTris.length / 6);
    }
    if (coneTris.length) {
      gl.uniform1f(this.locations.opacity, 0.16);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(coneTris), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.TRIANGLES, 0, coneTris.length / 6);
    }
    if (gridLines.length) {
      gl.uniform1f(this.locations.opacity, 0.88);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(gridLines), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.LINES, 0, gridLines.length / 6);
    }

    gl.depthMask(true);
    if (droneTris.length) {
      gl.uniform1f(this.locations.opacity, 0.94);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(droneTris), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.TRIANGLES, 0, droneTris.length / 6);
    }
    if (droneLines.length) {
      gl.uniform1f(this.locations.opacity, 1.0);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(droneLines), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.LINES, 0, droneLines.length / 6);
    }
    gl.disable(gl.BLEND);
    this.canvas.dataset.visionGrid = "true";
  }
  cameraState(width, height, aspect = width / height) {
    const state = { width, height, aspect, origin: this.mesh.origin_utm, center: this.center,
      yaw: this.yaw, pitch: this.pitch, scale: this.zoom / this.extent,
      fpv: !!(this.firstPerson && this.flightPose), focal: 1 / Math.tan(this.fov * Math.PI / 360) };
    if (state.fpv) {
      const { position: p, ahead: a } = this.flightPose, heading = Math.atan2(a[1] - p[1], a[0] - p[0]) + this.fpvYaw;
      const dist = this.fpvDistance || 58, lift = Math.max(14, dist * 0.44);
      const ex = p[0] - Math.cos(heading) * dist, ey = p[1] - Math.sin(heading) * dist;
      const groundZ = this.sampleElevation(ex, ey);
      state.eye = [ex - state.origin[0], ey - state.origin[1], Math.max(p[2] + lift, groundZ + 12)];
      state.forward = [Math.cos(heading) * Math.cos(this.fpvPitch), Math.sin(heading) * Math.cos(this.fpvPitch), Math.sin(this.fpvPitch)];
      state.right = [Math.sin(heading), -Math.cos(heading), 0];
      state.up = [state.right[1] * state.forward[2], -state.right[0] * state.forward[2], state.right[0] * state.forward[1] - state.right[1] * state.forward[0]];
    }
    return state;
  }
  applyCamera(locations, camera) {
    const gl = this.gl;
    gl.uniform3f(locations.center, ...camera.center);
    gl.uniform4f(locations.camera, camera.yaw, camera.pitch, camera.scale, 0);
    gl.uniform1f(locations.aspect, camera.aspect);
    gl.uniform1i(locations.firstPerson, camera.fpv ? 1 : 0);
    if (locations.opacity) gl.uniform1f(locations.opacity, 1.0);
    if (camera.fpv) {
      for (const key of ['eye', 'forward', 'right', 'up']) gl.uniform3f(locations[key], ...camera[key]);
      gl.uniform1f(locations.focal, camera.focal);
    }
  }
  drawAnimatedFire(camera) {
    const f = this.fireUtm, m = this.mesh, gl = this.gl;
    if (!f || !m) return;
    const ox = m.origin_utm[0], oy = m.origin_utm[1];
    const cx = f[0] - ox, cy = f[1] - oy;
    const cz = (Number.isFinite(f[2]) ? f[2] : this.sampleElevation(f[0], f[1])) + 0.8;
    const t = performance.now() * 0.001;
    const tris = [], lines = [];
    const pushV = (arr, pt, col) => arr.push(pt[0], pt[1], pt[2], col[0], col[1], col[2]);
    const pushTri = (arr, p1, p2, p3, col) => { pushV(arr, p1, col); pushV(arr, p2, col); pushV(arr, p3, col); };
    const pushLine = (arr, p1, p2, col) => { pushV(arr, p1, col); pushV(arr, p2, col); };
    const layers = [
      { r: 16, h: 36 + 9 * Math.sin(t * 7.2), col: [0.95, 0.22, 0.03], sway: 5.5, speed: 5.1, segs: 8 },
      { r: 10.5, h: 27 + 7 * Math.cos(t * 9.4), col: [1.0, 0.56, 0.06], sway: 4.0, speed: 6.8, segs: 7 },
      { r: 5.5, h: 18 + 5 * Math.sin(t * 13.1), col: [1.0, 0.92, 0.28], sway: 2.2, speed: 9.2, segs: 6 },
    ];
    for (let li = 0; li < layers.length; li++) {
      const L = layers[li];
      const apex = [
        cx + Math.sin(t * L.speed + li) * L.sway,
        cy + Math.cos(t * (L.speed * 0.85) + li) * L.sway,
        cz + L.h,
      ];
      for (let s = 0; s < L.segs; s++) {
        const a0 = (s / L.segs) * Math.PI * 2 + t * (li % 2 ? 1.2 : -0.9);
        const a1 = ((s + 1) / L.segs) * Math.PI * 2 + t * (li % 2 ? 1.2 : -0.9);
        const p0 = [cx + Math.cos(a0) * L.r, cy + Math.sin(a0) * L.r, cz];
        const p1 = [cx + Math.cos(a1) * L.r, cy + Math.sin(a1) * L.r, cz];
        pushTri(tris, p0, p1, apex, L.col);
      }
    }
    // Rising glowing embers & smoke puffs
    for (let e = 0; e < 7; e++) {
      const phase = ((t * 0.75 + e * 0.143) % 1);
      const ez = cz + 12 + phase * 48;
      const ex = cx + Math.sin(t * 3.1 + e * 1.9) * (6 + phase * 10);
      const ey = cy + Math.cos(t * 2.7 + e * 2.3) * (6 + phase * 10);
      const sz = 2.6 * (1 - phase * 0.5);
      const ecol = phase < 0.55 ? [1.0, 0.72, 0.15] : [0.42, 0.36, 0.34];
      pushTri(tris, [ex - sz, ey, ez], [ex + sz, ey, ez], [ex, ey, ez + sz * 1.6], ecol);
    }
    // Pulsing thermal ground rings
    for (let ri = 0; ri < 2; ri++) {
      const pPhase = ((t * 0.9 + ri * 0.5) % 1);
      const rad = 14 + pPhase * 34;
      const segs = 16;
      const rcol = [1.0, 0.25 + 0.35 * (1 - pPhase), 0.05];
      for (let s = 0; s < segs; s++) {
        const a0 = (s / segs) * Math.PI * 2, a1 = ((s + 1) / segs) * Math.PI * 2;
        pushLine(lines, [cx + Math.cos(a0) * rad, cy + Math.sin(a0) * rad, cz + 0.6], [cx + Math.cos(a1) * rad, cy + Math.sin(a1) * rad, cz + 0.6], rcol);
      }
    }
    gl.useProgram(this.program);
    this.applyCamera(this.locations, camera);
    this.bind(this.dynamic);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    if (tris.length) {
      gl.uniform1f(this.locations.opacity, 0.88);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(tris), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.TRIANGLES, 0, tris.length / 6);
    }
    if (lines.length) {
      gl.uniform1f(this.locations.opacity, 0.92);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(lines), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.LINES, 0, lines.length / 6);
    }
    gl.depthMask(true);
    gl.disable(gl.BLEND);
  }
  draw() {
    if (this.disposed) return;
    const gl = this.gl,
      c = this.canvas,
      m = this.mesh;
    if (!c.clientWidth || !c.clientHeight) return;
    const ratio = Math.min(devicePixelRatio || 1, 2),
      width = Math.round(c.clientWidth * ratio),
      height = Math.round(c.clientHeight * ratio);
    if (c.width !== width || c.height !== height) {
      c.width = width;
      c.height = height;
    }
    gl.viewport(0, 0, width, height);
    gl.clearColor(0.82, 0.89, 0.93, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    const camera = this.cameraState(c.clientWidth, c.clientHeight, width / height), fpv = camera.fpv;
    gl.useProgram(this.program);
    this.applyCamera(this.locations, camera);
    c.dataset.camera = fpv ? "drone" : "orbit";
    // A commune-specific typed terrain replaces only its visual representation.
    // The original mesh remains available for coordinates and unknown-elevation checks.
    if (!Object.hasOwn(this.groups, "terrain")) {
      this.bind(this.terrain.buffer);
      gl.drawArrays(this.terrain.mode, 0, this.terrain.count);
    }
    let rendered = 0;
    for (const [key, buffers] of Object.entries(this.groups))
      if (this.visibility[key])
        for (const b of buffers) {
          this.bindItem(b);
          gl.drawArrays(b.mode, 0, b.count);
          rendered += b.count;
        }
    c.dataset.sceneVertices = String(rendered);
    c.dataset.sceneLayers = Object.keys(this.groups)
      .filter((k) => this.visibility[k])
      .join(",");
    for (const item of this.routeBuffers) {
      if (fpv && item.symbol) continue;
      if (item.screenRoute) {
        const locations = this.routeLocations;
        gl.useProgram(this.routeProgram); this.applyCamera(locations, camera);
        gl.uniform2f(locations.viewport, width, height);
        gl.uniform1f(locations.routeWidth, (item.symbol ? 1 : item.widthPx) * ratio);
        gl.uniform1i(locations.symbol, item.symbol ? 1 : 0);
        gl.uniform3f(locations.routeColor, ...item.color);
        gl.bindBuffer(gl.ARRAY_BUFFER, item.buffer);
        for (const [name, components, offset] of [['routeStart', 3, 0], ['routeEnd', 3, 12], ['corner', 2, 24]]) {
          gl.enableVertexAttribArray(locations[name]); gl.vertexAttribPointer(locations[name], components, gl.FLOAT, false, 32, offset);
        }
        if (item.symbol) {
          // Route-colored outline plus ivory head makes direction legible even
          // where a route runs over a similarly colored land-cover surface.
          gl.uniform1f(locations.routeWidth, 1.4 * ratio);
          gl.drawArrays(item.mode, 0, item.count);
          gl.uniform1f(locations.routeWidth, ratio);
          gl.uniform3f(locations.routeColor, 1, .99, .90);
        }
      } else {
        gl.useProgram(this.program); this.applyCamera(this.locations, camera); this.bindItem(item);
      }
      gl.drawArrays(item.mode, 0, item.count);
    }
    if (this.marker && !fpv && !this.annotationLayer) {
      const p = this.marker;
      gl.useProgram(this.program); this.applyCamera(this.locations, camera);
      this.bind(this.dynamic);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([
          p[0] - m.origin_utm[0],
          p[1] - m.origin_utm[1],
          p[2] + 4,
          1,
          0.3,
          0.1,
        ]),
        gl.DYNAMIC_DRAW,
      );
      gl.drawArrays(gl.POINTS, 0, 1);
    }
    if (this.forbiddenZoneBuffers.length) {
      gl.useProgram(this.program);
      this.applyCamera(this.locations, camera);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.depthMask(false);
      for (const zb of this.forbiddenZoneBuffers) {
        gl.uniform1f(this.locations.opacity, zb.opacity ?? 0.3);
        this.bindItem(zb);
        gl.drawArrays(zb.mode, 0, zb.count);
      }
      gl.depthMask(true);
      gl.disable(gl.BLEND);
    }
    if (this.flightPose || this.plannedCorridor?.length || this.coverageTrail?.length) this.drawDroneVision(camera);
    if (this.fireUtm) this.drawAnimatedFire(camera);
    this.updateAnnotations(camera);
    c.dataset.zoom = this.zoom.toFixed(6);
    c.dataset.fov = this.fov.toFixed(3);
    c.dataset.routeScreenWidths = JSON.stringify(this.routeBuffers.filter((item) => item.screenRoute && !item.symbol).map((item) => item.widthPx));
    c.dataset.terrainStyle = 'vertex-normal-lighting-v1';
  }
}
