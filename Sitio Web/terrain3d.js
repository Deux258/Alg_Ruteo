// Metric DSM + local OSM/CONAF geometry. No remote 3D service or token.
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
    this.fpvPitch = -0.18;
    this.fov = 70;
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
      `attribute vec3 position;attribute vec3 color;varying vec3 tint;uniform vec3 center;uniform vec4 camera;uniform float aspect;uniform bool firstPerson;uniform vec3 eye;uniform vec3 forward;uniform vec3 right;uniform vec3 up;uniform float focal;void main(){if(firstPerson){vec3 p=position-eye;float z=dot(p,forward);gl_Position=vec4(dot(p,right)*focal/aspect,dot(p,up)*focal,1.000100005*z-2.000100005,z);}else{vec3 p=position-center;float x=cos(camera.x)*p.x-sin(camera.x)*p.y;float y=sin(camera.x)*p.x+cos(camera.x)*p.y;gl_Position=vec4(x*camera.z,(y*sin(camera.y)+p.z*cos(camera.y))*camera.z*aspect,(y*cos(camera.y)-p.z*sin(camera.y))*camera.z*.15,1.);}gl_PointSize=13.;tint=color;}`,
    );
    const fs = shader(
      gl.FRAGMENT_SHADER,
      `precision mediump float;varying vec3 tint;void main(){gl_FragColor=vec4(tint,1.);}`,
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
    };
    const vertices = [];
    const { width, height, x, y, elevations } = mesh;
    const hs = elevations.filter((v) => v !== null);
    this.mean = hs.length ? hs.reduce((a, b) => a + b, 0) / hs.length : 0;
    const vertex = (i, j) => {
      const h = elevations[j * width + i];
      return !Number.isFinite(h) ? null : [x[i], y[j], h];
    };
    for (let j = 0; j < height - 1; j++)
      for (let i = 0; i < width - 1; i++)
        for (const tri of [
          [vertex(i, j), vertex(i + 1, j), vertex(i, j + 1)],
          [vertex(i + 1, j), vertex(i + 1, j + 1), vertex(i, j + 1)],
        ]) {
          if (tri.some((v) => !v)) continue;
          const z = tri.reduce((s, v) => s + v[2], 0) / 3;
          const shade = this.shade(tri);
          const c = [
            (0.59 + z / 10000) * shade,
            (0.63 + z / 12000) * shade,
            0.48 * shade,
          ];
          for (const v of tri) vertices.push(...v, ...c);
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
          for (let k = 0; k < count; k++)
            target.push(
              ...positions.slice(i + k * 3, i + k * 3 + 3),
              ...batch.color.map((c) => c * shade),
            );
        }
      }
      this.groups[key] = [
        this.makeBuffer(triangles, gl.TRIANGLES),
        this.makeBuffer(lines, gl.LINES),
      ];
      this.visibility[key] = true;
    }
    this.dynamic = gl.createBuffer();
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
        if (this.firstPerson) {
          this.fov = Math.max(40, Math.min(100, this.fov + e.deltaY * 0.025));
          this.draw();
          return;
        }
        this.zoom = Math.max(
          0.3,
          Math.min(60, this.zoom * Math.exp(-e.deltaY * 0.001)),
        );
        this.draw();
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
    this.deleteBuffers([this.terrain, ...this.routeBuffers]);
    for (const buffers of Object.values(this.groups))
      this.deleteBuffers(buffers);
    this.gl.deleteBuffer(this.dynamic);
    this.gl.deleteProgram(this.program);
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
    this.routeBuffers = lines.map((line) => {
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
      if (line.point) line.points.forEach(add);
      else
        for (let i = 1; i < line.points.length; i++) {
          const a = line.points[i - 1],
            b = line.points[i];
          if (!a.every(Number.isFinite) || !b.every(Number.isFinite)) continue;
          const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
          if (!d) continue;
          const dx = (-(b[1] - a[1]) / d) * (line.width || 1.5),
            dy = ((b[0] - a[0]) / d) * (line.width || 1.5);
          const v = [a[0] + dx, a[1] + dy, a[2]],
            w = [a[0] - dx, a[1] - dy, a[2]],
            x = [b[0] + dx, b[1] + dy, b[2]],
            y = [b[0] - dx, b[1] - dy, b[2]];
          [v, w, x, x, w, y].forEach(add);
        }
      return {
        ...this.makeBuffer(data, line.point ? gl.POINTS : gl.TRIANGLES),
        target: line.target,
        point: line.point,
      };
    });
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
    this.draw();
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
      this.fpvPitch = -0.18;
    }
    this.draw();
  }
  setFlightPose(position, ahead, follow = false) {
    this.marker = position;
    this.flightPose = { position, ahead };
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
    gl.clearColor(0.88, 0.92, 0.91, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.useProgram(this.program);
    gl.uniform3f(this.locations.center, ...this.center);
    gl.uniform4f(
      this.locations.camera,
      this.yaw,
      this.pitch,
      this.zoom / this.extent,
      0,
    );
    gl.uniform1f(this.locations.aspect, width / height);
    const fpv = this.firstPerson && this.flightPose;
    gl.uniform1i(this.locations.firstPerson, fpv ? 1 : 0);
    c.dataset.camera = fpv ? "drone" : "orbit";
    if (fpv) {
      const { position: p, ahead: a } = this.flightPose,
        heading = Math.atan2(a[1] - p[1], a[0] - p[0]) + this.fpvYaw;
      const forward = [
          Math.cos(heading) * Math.cos(this.fpvPitch),
          Math.sin(heading) * Math.cos(this.fpvPitch),
          Math.sin(this.fpvPitch),
        ],
        right = [Math.sin(heading), -Math.cos(heading), 0],
        up = [
          right[1] * forward[2],
          -right[0] * forward[2],
          right[0] * forward[1] - right[1] * forward[0],
        ];
      gl.uniform3f(
        this.locations.eye,
        p[0] - m.origin_utm[0],
        p[1] - m.origin_utm[1],
        p[2] + 1.2,
      );
      gl.uniform3f(this.locations.forward, ...forward);
      gl.uniform3f(this.locations.right, ...right);
      gl.uniform3f(this.locations.up, ...up);
      gl.uniform1f(
        this.locations.focal,
        1 / Math.tan((this.fov * Math.PI) / 360),
      );
    }
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
      if (fpv && !item.target && !item.point) continue;
      this.bindItem(item);
      gl.drawArrays(item.mode, 0, item.count);
    }
    if (this.marker && !fpv) {
      const p = this.marker;
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
  }
}
