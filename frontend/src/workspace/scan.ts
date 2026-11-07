/** Point-cloud rendering of the real part photo. Runs only while assembling or scanning; the <img> carries the rest state. */
const GRID = 190

const VERTEX = `
precision highp float;
attribute vec2 aGrid;
attribute vec3 aSeed;
uniform sampler2D uPhoto;
uniform vec2 uFit;
uniform vec2 uTilt;
uniform float uScatter;
uniform float uDepth;
uniform float uBeam;
uniform float uSize;
varying vec4 vColor;

void main() {
  vec3 photo = texture2D(uPhoto, aGrid).rgb;
  float light = dot(photo, vec3(0.3, 0.59, 0.11));
  vec3 p = vec3((aGrid.x - 0.5) * 2.0 * uFit.x, (0.5 - aGrid.y) * 2.0 * uFit.y, (light - 0.25) * uDepth);
  p += (aSeed - 0.5) * 2.4 * uScatter;
  float cy = cos(uTilt.x);
  float sy = sin(uTilt.x);
  float cx = cos(uTilt.y);
  float sx = sin(uTilt.y);
  p = vec3(cy * p.x + sy * p.z, p.y, -sy * p.x + cy * p.z);
  p = vec3(p.x, cx * p.y - sx * p.z, sx * p.y + cx * p.z);
  float glow = uBeam < 0.0 ? 0.0 : smoothstep(0.05, 0.0, abs(aGrid.y - uBeam));
  float alpha = smoothstep(0.06, 0.14, light) * (1.0 - 0.5 * uScatter);
  vec3 tone = mix(photo * 1.25 + 0.05, vec3(1.0, 0.81, 0.1), glow);
  vColor = vec4(tone * alpha, alpha);
  gl_Position = vec4(p.xy, 0.0, 1.0 - p.z * 0.35);
  gl_PointSize = uSize * (1.0 + glow * 1.5);
}`

const FRAGMENT = `
precision mediump float;
varying vec4 vColor;

void main() {
  vec2 p = gl_PointCoord - 0.5;
  if (dot(p, p) > 0.25) discard;
  gl_FragColor = vColor;
}`

export type ScanMode = 'assemble' | 'scan' | 'settle'

const easeOut = (value: number) => 1 - (1 - value) ** 3

function shader(gl: WebGLRenderingContext, type: number, source: string) {
  const item = gl.createShader(type)
  if (!item) return null
  gl.shaderSource(item, source)
  gl.compileShader(item)
  return gl.getShaderParameter(item, gl.COMPILE_STATUS) ? item : null
}

export function motionAllowed() {
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export class PointScan {
  private gl: WebGLRenderingContext
  private program: WebGLProgram
  private buffers: WebGLBuffer[] = []
  private texture: WebGLTexture | null = null
  private uniforms: Record<string, WebGLUniformLocation | null> = {}
  private aspect = 1
  private ready = false
  private mode: ScanMode | null = null
  private started = 0
  private frame = 0
  private finish: (() => void) | undefined
  private pointer = { x: 0, y: 0 }
  private tilt = { x: 0, y: 0 }
  private count = GRID * GRID

  static create(canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: true, antialias: false, powerPreference: 'low-power' })
    if (!gl || gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS) < 1) return null
    const vertex = shader(gl, gl.VERTEX_SHADER, VERTEX)
    const fragment = shader(gl, gl.FRAGMENT_SHADER, FRAGMENT)
    const program = gl.createProgram()
    if (!vertex || !fragment || !program) return null
    gl.attachShader(program, vertex)
    gl.attachShader(program, fragment)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null
    return new PointScan(gl, program)
  }

  private constructor(gl: WebGLRenderingContext, program: WebGLProgram) {
    this.gl = gl
    this.program = program
    gl.useProgram(program)
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.clearColor(0, 0, 0, 0)
    const grid = new Float32Array(this.count * 2)
    const seed = new Float32Array(this.count * 3)
    for (let index = 0; index < this.count; index++) {
      grid[index * 2] = (index % GRID) / (GRID - 1)
      grid[index * 2 + 1] = Math.floor(index / GRID) / (GRID - 1)
      seed[index * 3] = Math.random()
      seed[index * 3 + 1] = Math.random()
      seed[index * 3 + 2] = Math.random()
    }
    this.attribute('aGrid', grid, 2)
    this.attribute('aSeed', seed, 3)
    for (const name of ['uPhoto', 'uFit', 'uTilt', 'uScatter', 'uDepth', 'uBeam', 'uSize']) this.uniforms[name] = gl.getUniformLocation(program, name)
    this.resize()
  }

  private attribute(name: string, data: Float32Array, size: number) {
    const { gl } = this
    const buffer = gl.createBuffer()
    if (!buffer) return
    this.buffers.push(buffer)
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW)
    const location = gl.getAttribLocation(this.program, name)
    gl.enableVertexAttribArray(location)
    gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0)
  }

  async load(url: string) {
    const photo = new Image()
    photo.src = url
    await photo.decode()
    const { gl } = this
    if (this.texture) gl.deleteTexture(this.texture)
    this.texture = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, this.texture)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, photo)
    this.aspect = photo.naturalWidth / Math.max(1, photo.naturalHeight)
    this.ready = true
  }

  resize() {
    const canvas = this.gl.canvas as HTMLCanvasElement
    const scale = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = Math.max(1, Math.round(canvas.clientWidth * scale))
    canvas.height = Math.max(1, Math.round(canvas.clientHeight * scale))
    this.gl.viewport(0, 0, canvas.width, canvas.height)
  }

  aim(x: number, y: number) {
    this.pointer = { x, y }
  }

  play(mode: ScanMode, finish?: () => void) {
    this.mode = mode
    this.finish = finish
    this.started = performance.now()
    if (!this.frame) this.frame = requestAnimationFrame(this.tick)
  }

  private tick = (time: number) => {
    const age = time - this.started
    let scatter = 0
    let depth = 0
    let beam = -1
    let done = false
    if (this.mode === 'assemble') {
      const progress = Math.min(1, age / 1300)
      const eased = easeOut(progress)
      scatter = 1 - eased
      depth = 0.7 * (1 - eased)
      this.tilt = { x: 0.5 * (1 - eased), y: 0.2 * (1 - eased) }
      done = progress >= 1
    } else if (this.mode === 'scan') {
      const ramp = easeOut(Math.min(1, age / 520))
      depth = 0.62 * ramp
      const sweep = (age / 1500) % 2
      beam = sweep < 1 ? sweep : 2 - sweep
      this.tilt = { x: (Math.sin(age / 1400) * 0.3 + this.pointer.x * 0.35) * ramp, y: (0.2 + this.pointer.y * 0.25) * ramp }
    } else {
      const progress = Math.min(1, age / 520)
      const eased = easeOut(progress)
      depth = 0.62 * (1 - eased)
      this.tilt = { x: this.tilt.x * (1 - eased), y: this.tilt.y * (1 - eased) }
      done = progress >= 1
    }
    this.draw(scatter, depth, beam)
    if (done) {
      this.frame = 0
      const finish = this.finish
      this.finish = undefined
      this.mode = null
      finish?.()
      return
    }
    this.frame = requestAnimationFrame(this.tick)
  }

  private draw(scatter: number, depth: number, beam: number) {
    const { gl, uniforms } = this
    gl.clear(gl.COLOR_BUFFER_BIT)
    if (!this.ready) return
    const canvas = gl.canvas as HTMLCanvasElement
    const box = canvas.width / Math.max(1, canvas.height)
    gl.uniform1i(uniforms.uPhoto, 0)
    gl.uniform2f(uniforms.uFit, Math.min(1, this.aspect / box) * 0.97, Math.min(1, box / this.aspect) * 0.97)
    gl.uniform2f(uniforms.uTilt, this.tilt.x, this.tilt.y)
    gl.uniform1f(uniforms.uScatter, scatter)
    gl.uniform1f(uniforms.uDepth, depth)
    gl.uniform1f(uniforms.uBeam, beam)
    gl.uniform1f(uniforms.uSize, Math.max(1.6, (Math.min(canvas.width, canvas.height) / GRID) * 0.72))
    gl.drawArrays(gl.POINTS, 0, this.count)
  }

  dispose() {
    cancelAnimationFrame(this.frame)
    this.frame = 0
    this.finish = undefined
    for (const buffer of this.buffers) this.gl.deleteBuffer(buffer)
    if (this.texture) this.gl.deleteTexture(this.texture)
    this.gl.deleteProgram(this.program)
  }
}
