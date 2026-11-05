// Metric DSM + local OSM/CONAF geometry. No remote 3D service or token.
export class TerrainView {
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
      `attribute vec3 position;attribute vec3 color;varying vec3 tint;uniform vec3 center;uniform vec4 camera;uniform float aspect;void main(){vec3 p=position-center;float x=cos(camera.x)*p.x-sin(camera.x)*p.y;float y=sin(camera.x)*p.x+cos(camera.x)*p.y;gl_Position=vec4(x*camera.z,(y*sin(camera.y)+p.z*cos(camera.y))*camera.z*aspect,(y*cos(camera.y)-p.z*sin(camera.y))*camera.z*.15,1.);gl_PointSize=13.;tint=color;}`,
    );
    const fs = shader(
      gl.FRAGMENT_SHADER,
      `precision mediump float;varying vec3 tint;void main(){gl_FragColor=vec4(tint,1.);}`,
    );
    const program = (this.program = gl.createProgram());
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(program));
    this.locations = {
      position: gl.getAttribLocation(program, "position"),
      color: gl.getAttribLocation(program, "color"),
      center: gl.getUniformLocation(program, "center"),
      camera: gl.getUniformLocation(program, "camera"),
      aspect: gl.getUniformLocation(program, "aspect"),
    };
    const vertices = [];
    const { width, height, x, y, elevations } = mesh;
    const hs = elevations.filter((v) => v !== null);
    this.mean = hs.reduce((a, b) => a + b, 0) / hs.length;
    const vertex = (i, j) => {
      const h = elevations[j * width + i];
      return h === null ? null : [x[i], y[j], h];
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
    let drag = null;
    canvas.addEventListener("pointerdown", (e) => {
      drag = { x: e.clientX, y: e.clientY, pan: e.shiftKey || e.button === 2 };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    canvas.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x,
        dy = e.clientY - drag.y;
      if (drag.pan) {
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
      canvas.addEventListener(event, () => (drag = null));
    canvas.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
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
  reset() {
    const m = this.mesh;
    this.center = [m.x.at(-1) / 2, m.y.at(-1) / 2, this.mean];
    this.extent = Math.max(m.x.at(-1), m.y.at(-1));
    this.zoom = 1.6;
    this.focused = false;
    this.draw();
  }
  focusRoutes() {
    const points = this.lines.filter((l) => !l.point).flatMap((l) => l.points);
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
  draw() {
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
    this.bind(this.terrain.buffer);
    gl.drawArrays(this.terrain.mode, 0, this.terrain.count);
    let rendered = 0;
    for (const [key, buffers] of Object.entries(this.groups))
      if (this.visibility[key])
        for (const b of buffers) {
          this.bind(b.buffer);
          gl.drawArrays(b.mode, 0, b.count);
          rendered += b.count;
        }
    c.dataset.sceneVertices = String(rendered);
    c.dataset.sceneLayers = Object.keys(this.groups)
      .filter((k) => this.visibility[k])
      .join(",");
    for (const line of this.lines) {
      const data = [];
      const add = (p) =>
        data.push(
          p[0] - m.origin_utm[0],
          p[1] - m.origin_utm[1],
          p[2] + 2,
          ...line.color,
        );
      if (line.point) {
        for (const p of line.points) add(p);
      } else
        for (let i = 1; i < line.points.length; i++) {
          const a = line.points[i - 1],
            b = line.points[i],
            d = Math.hypot(b[0] - a[0], b[1] - a[1]);
          if (!d) continue;
          const dx = (-(b[1] - a[1]) / d) * 1.5,
            dy = ((b[0] - a[0]) / d) * 1.5;
          const v = [a[0] + dx, a[1] + dy, a[2]],
            w = [a[0] - dx, a[1] - dy, a[2]],
            x = [b[0] + dx, b[1] + dy, b[2]],
            y = [b[0] - dx, b[1] - dy, b[2]];
          for (const p of [v, w, x, x, w, y]) add(p);
        }
      this.bind(this.dynamic);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.DYNAMIC_DRAW);
      gl.drawArrays(line.point ? gl.POINTS : gl.TRIANGLES, 0, data.length / 6);
    }
    if (this.marker) {
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
