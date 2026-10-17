import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'

/**
 * The redesign's one atmospheric effect (Horizon design system, design_decisions
 * E22): the template's black hole, ray-marched in a fragment shader. A lensed,
 * Doppler-beamed accretion disc (warm amber to cream) rings a dark sphere on
 * black, sitting at the right of the shared PageHeader band so the title on the
 * left reads over dark sky. The band is sticky, so it stays on screen.
 *
 * Ported from the template's FRAG_SIM in frontend/template/redesign-template.html
 * (INSTALANDING.AI "Event Horizon Orbital Page", MIT). Dropped: the lensed text
 * banner, drag/scroll camera, bloom, chromatic offset and grain.
 *
 * One pass, on purpose: this is the phone's launch screen. The template renders
 * the sim into a render target and then runs bright/blur/composite passes; here
 * the composite's grade (exposure, warm tint, desaturate, ACES, gamma, vignette)
 * is applied inline at the end of the one pass, so there are no extra textures,
 * framebuffers or fill-rate. It is raw WebGL1, no three.js.
 *
 * Budget rules:
 *  - ray steps 90 on touch, 140 otherwise (template: 230); render scale 0.75 on
 *    touch, min(devicePixelRatio, 1.25) otherwise; ~30 fps on touch;
 *  - adaptive, as in the template: if the first 60 frames average slower than
 *    28 fps, halve the steps and drop the scale to 0.6 once; if the next 60 are
 *    still slow, stop the loop and keep the last frame as a still image;
 *  - pauses while the tab is hidden or the canvas is off-screen;
 *  - one still frame (template "quieto" moment, uTime 12) under
 *    prefers-reduced-motion;
 *  - light theme: the hole is a night object, so no GL context at all, only the
 *    CSS glow below. No WebGL, a failed compile or a lost context do the same.
 * Everything (RAF, observers, the GL context) is torn down on unmount so route
 * changes never leak a render loop.
 */

const VERT = 'attribute vec2 position;void main(){gl_Position=vec4(position,0,1);}'

// STEPS_MAX is the compile-time loop bound (GLSL ES 1.00 needs a constant);
// uPasos is the runtime budget and breaks out early.
const STEPS_MAX = 160
const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform float uTime, uCamDist, uYaw, uPitch;
uniform float uVel, uTemp, uDoppler, uFondo, uPasos;
uniform vec2  uRes;
uniform vec2  uCenter;
uniform float uZoom;

float hash21(vec2 p){
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float hash31(vec3 p){
  p = fract(p * 0.1031);
  p += dot(p, p.zyx + 31.32);
  return fract((p.x + p.y) * p.z);
}
float noise2(vec2 p){
  vec2 i = floor(p); vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
float fbm(vec2 p){
  float v = 0.0; float a = 0.55;
  for(int i = 0; i < 4; i++){
    v += a * noise2(p);
    p = p * 2.13 + vec2(13.7, 7.1);
    a *= 0.5;
  }
  return v;
}

vec3 cielo(vec3 rd){
  vec3 col = vec3(0.0);
  for(int capa = 0; capa < 4; capa++){
    float fc = float(capa);
    float esc = 140.0 + fc * 200.0;
    vec3 q = rd * esc;
    vec3 id = floor(q);
    float h = hash31(id);
    if(h > 0.990 - fc * 0.0025){
      vec3 c = fract(q) - 0.5;
      float d = length(c);
      float b = 1.0 - smoothstep(0.0, 0.5, d);
      b = pow(b, 12.0) * (0.5 + 1.6 * fract(h * 91.7));
      vec3 tinte = mix(vec3(0.65, 0.78, 1.0), vec3(1.0, 0.83, 0.62), fract(h * 53.1));
      if(fract(h * 17.3) > 0.90) b *= 6.0;
      col += b * tinte * 2.0;
    }
  }
  float n1 = fbm(rd.xy * 2.0 + rd.z * 1.3);
  float n2 = fbm(rd.zy * 3.1 - rd.x * 1.7 + 5.0);
  vec3 gas = vec3(0.020, 0.045, 0.110) * pow(n1, 2.6) * 0.50
           + vec3(0.090, 0.040, 0.022) * pow(n2, 3.2) * 0.40;
  float banda = exp(-pow((rd.y + 0.16) * 2.6, 2.0));
  float polvo = fbm(rd.xz * 5.0 + 2.3) * 0.7 + fbm(rd.xz * 11.0) * 0.5;
  gas += (vec3(0.05, 0.06, 0.10) + vec3(0.06, 0.04, 0.02) * polvo) * banda * polvo * 0.30;
  float oscuro = smoothstep(0.45, 0.75, fbm(rd.xz * 7.0 + 9.1));
  gas *= mix(1.0, 0.25, oscuro * banda);
  col += gas * uFondo;
  return col;
}

vec3 colorGas(float r, float rIn, float rOut){
  float t = clamp((r - rIn) / (rOut - rIn), 0.0, 1.0);
  vec3 nucleo = mix(vec3(1.00, 0.98, 0.94), vec3(0.80, 0.90, 1.00), uTemp);
  vec3 medio  = vec3(1.00, 0.60, 0.20);
  vec3 borde  = vec3(0.50, 0.14, 0.03);
  vec3 c = mix(nucleo, medio, smoothstep(0.0, 0.40, t));
  return mix(c, borde, smoothstep(0.40, 1.0, t));
}

vec4 disco(vec3 p, vec3 rd, float rIn, float rOut){
  float r = length(p.xz);
  if(r < rIn - 0.4 || r > rOut) return vec4(0.0);
  float H = 0.085 + 0.34 * pow(clamp((r - 2.0) / 11.0, 0.0, 1.0), 1.7);
  float y = p.y / H;
  if(abs(y) > 3.5) return vec4(0.0);
  float vertical = exp(-y * y * 2.1);
  float bruma = exp(-y * y * 0.45) * 0.16;

  float ang = atan(p.z, p.x);
  float omega = uVel * 0.9 / pow(r, 1.5);
  float a1 = ang + uTime * omega * 9.0;

  float brazos = fbm(vec2(r * 2.2, a1 * 2.4));
  float hebras = fbm(vec2(r * 14.0 - uTime * 0.05, a1 * 1.3) + 7.3);
  float hilos  = noise2(vec2(r * 46.0, a1 * 4.0));
  float espiral = fbm(vec2(r * 5.0, a1 * 3.5 + r * 2.2));
  float grumos  = pow(noise2(vec2(r * 3.5, a1 * 6.0)), 3.0);
  float dens = brazos * 0.42 + hebras * 0.38 + hilos * 0.14
             + espiral * 0.30 + grumos * 0.55;
  dens = smoothstep(0.12, 1.05, dens);
  dens = dens * dens * (1.2 + 0.5 * hebras);
  dens = dens * vertical + bruma * (0.4 + 0.6 * brazos);
  dens *= smoothstep(rIn - 0.4, rIn + 0.45, r);
  dens *= 1.0 - smoothstep(rOut - 2.6, rOut, r);

  if(dens < 0.003) return vec4(0.0);

  float perfil = pow(3.0 / r, 1.9);

  float beta = clamp(sqrt(0.5 / max(r - 1.0, 0.4)), 0.0, 0.85) * min(uVel, 1.6);
  vec3 velDir = normalize(vec3(-p.z, 0.0, p.x));
  float coseno = dot(rd, velDir);
  float dop = 1.0 / max(1.0 - beta * coseno, 0.15);
  float beaming = mix(1.0, pow(dop, 3.0), uDoppler);
  float shift = uDoppler * clamp(beta * coseno, -1.0, 1.0);

  float zGrav = sqrt(max(1.0 - 1.0 / r, 0.05));
  beaming *= mix(1.0, zGrav * zGrav, uDoppler * 0.7);

  vec3 col = colorGas(r, rIn, rOut);
  col = mix(col, vec3(1.0, 0.99, 0.95), clamp(perfil * 0.45, 0.0, 0.9));
  col = mix(col, vec3(0.72, 0.84, 1.00), max(shift, 0.0) * 0.55);
  col = mix(col, vec3(0.85, 0.25, 0.07), max(-shift, 0.0) * 0.6);

  return vec4(col * perfil * beaming * dens, dens);
}

vec3 aces(vec3 x){
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

void main(){
  // Screen coords relative to the hole's centre, band HEIGHT as the unit, so the
  // hole keeps its shape on any aspect; uZoom > 1 shrinks it.
  vec2 uv = (gl_FragCoord.xy - uCenter * uRes) / uRes.y * uZoom;

  float cy = cos(uYaw); float sy = sin(uYaw);
  float cp = cos(uPitch); float sp = sin(uPitch);
  vec3 ro = uCamDist * vec3(cy * cp, sp, sy * cp);
  vec3 fw = normalize(-ro);
  vec3 rt = normalize(cross(fw, vec3(0.0, 1.0, 0.0)));
  vec3 up = cross(rt, fw);
  vec3 rd = normalize(fw * 1.5 + uv.x * rt + uv.y * up);

  vec3 p = ro;
  vec3 v = rd;
  vec3 hVec = cross(p, v);
  float h2 = dot(hVec, hVec);

  float rIn = 3.0; float rOut = 13.0;

  vec3 col = vec3(0.0);
  float transmit = 1.0;
  float capturado = 0.0;
  float minR = 100000.0;

  for(int i = 0; i < ${STEPS_MAX}; i++){
    if(float(i) >= uPasos) break;

    float r2 = dot(p, p);
    float r  = sqrt(r2);
    minR = min(minR, r);

    float dt = clamp(r * 0.065, 0.018, 0.42);
    float grosor = 0.085 + 0.34 * pow(clamp((r - 2.0) / 11.0, 0.0, 1.0), 1.7);
    if(abs(p.y) < grosor * 3.5 && r > rIn - 1.0 && r < rOut + 0.5) dt *= 0.45;

    vec3 a = -1.5 * h2 * p / (r2 * r2 * r);
    v += a * dt;
    p += v * dt;

    if(dot(p, p) < 1.0){ capturado = 1.0; break; }

    if(transmit > 0.012){
      vec4 d = disco(p, normalize(v), rIn, rOut);
      if(d.a > 0.0){
        col += d.rgb * transmit * dt * 4.6;
        transmit *= exp(-d.a * dt * 2.8);
      }
    }

    if(dot(p, p) > 1400.0) break;
  }

  if(capturado < 0.5 && transmit > 0.012){
    col += cielo(normalize(v)) * transmit;
  }

  float halo = exp(-abs(minR - 1.5) * 3.0);
  col += vec3(1.0, 0.80, 0.52) * halo * 0.45 * mix(1.0, 0.35, capturado);
  col += vec3(1.0, 0.62, 0.32) * exp(-minR * 0.34) * 0.10;

  // The template's composite grade, inline. uExpo is 1.0 there (no exposure
  // control is wired up), so it is not a uniform here.
  col *= vec3(1.06, 0.99, 0.88);
  float lum = dot(col, vec3(0.299, 0.587, 0.114));
  col = mix(vec3(lum), col, 0.92);
  col = aces(col);
  col = pow(col, vec3(1.0 / 1.10));
  col *= 1.0 - smoothstep(0.45, 1.05, length(uv)) * 0.55;

  gl_FragColor = vec4(col, 1.0);
}
`

// Fixed camera: the template's defaults (it orbits slowly and so do we).
const CAM_DIST = 27
const CAM_PITCH = 0.12
const ORBIT_RATE = 0.04 // rad/s, the template's auto-orbit
const STILL_TIME = 12 // the template's "quieto" moment, for reduced motion

// Where the hole sits in the band (0-1 coords, y up from the bottom) and how big.
// uZoom scales screen units into ray units: the template's framing is zoom 1
// (ring outer diameter about 1.44 band heights). These are close-ups: the ring
// overflows the band and is cropped by it, like the template's hero.
const DESKTOP = { cx: 0.64, cy: 0.5, zoom: 0.62 }
const PHONE = { cx: 0.84, cy: 0.5, zoom: 0.62 }
const PHONE_MAX_W = 640 // matches Tailwind `sm`

const STEPS_TOUCH = 90
const STEPS_DESKTOP = 140
const SAMPLE_FRAMES = 60 // frames averaged before judging performance
const SLOW_FRAME_MS = 1000 / 28
const FALLBACK_DPR = 0.6

// Keeps the left ~30% essentially clear for the title and fades the bottom edge
// into the band's border. Alpha only; the colour in a mask is irrelevant.
const MASK_X = 'linear-gradient(90deg, transparent 0%, rgba(0,0,0,.25) 22%, #000 48%)'
const MASK_Y = 'linear-gradient(180deg, #000 70%, transparent 100%)'
const MASK = `${MASK_X}, ${MASK_Y}`

export default function EventHorizon({ className }) {
  const { theme } = useTheme()
  const night = theme !== 'light'
  const hostRef = useRef(null)
  const [mode, setMode] = useState('pending') // pending → on | off

  useEffect(() => {
    if (!night) return undefined // light theme: no GL context, CSS glow only
    const host = hostRef.current
    if (!host) return undefined
    setMode('pending') // a re-run (theme back to dark) may recover from 'off'
    // The canvas is created per effect run: cleanup loses its GL context, and
    // getContext on a lost canvas returns the dead context (StrictMode runs
    // effect, cleanup, effect on the same element otherwise).
    const canvas = document.createElement('canvas')
    canvas.className = 'absolute inset-0 h-full w-full transition-opacity duration-[2400ms] ease-signal'
    canvas.style.opacity = '0'
    canvas.style.webkitMaskImage = MASK
    canvas.style.maskImage = MASK
    canvas.style.webkitMaskComposite = 'source-in'
    canvas.style.maskComposite = 'intersect'
    host.appendChild(canvas)
    const removeCanvas = () => canvas.remove()
    let gl = null
    try {
      const opts = { alpha: false, antialias: false, depth: false, stencil: false, powerPreference: 'low-power' }
      gl = canvas.getContext('webgl', opts) || canvas.getContext('experimental-webgl', opts)
    } catch {
      gl = null
    }
    if (!gl) {
      removeCanvas()
      setMode('off')
      return undefined
    }

    const compile = (type, src) => {
      const sh = gl.createShader(type)
      gl.shaderSource(sh, src)
      gl.compileShader(sh)
      return gl.getShaderParameter(sh, gl.COMPILE_STATUS) ? sh : null
    }
    const vs = compile(gl.VERTEX_SHADER, VERT)
    const fs = compile(gl.FRAGMENT_SHADER, FRAG)
    const prog = vs && fs ? gl.createProgram() : null
    if (prog) {
      gl.attachShader(prog, vs)
      gl.attachShader(prog, fs)
      gl.linkProgram(prog)
    }
    if (!prog || !gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      gl.getExtension('WEBGL_lose_context')?.loseContext()
      removeCanvas()
      setMode('off')
      return undefined
    }
    gl.useProgram(prog)

    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const aPos = gl.getAttribLocation(prog, 'position')
    gl.enableVertexAttribArray(aPos)
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0)

    const u = (name) => gl.getUniformLocation(prog, name)
    const uTime = u('uTime')
    const uYaw = u('uYaw')
    const uRes = u('uRes')
    const uCenter = u('uCenter')
    const uZoom = u('uZoom')
    const uPasos = u('uPasos')
    gl.uniform1f(u('uCamDist'), CAM_DIST)
    gl.uniform1f(u('uPitch'), CAM_PITCH)
    gl.uniform1f(u('uVel'), 1)
    gl.uniform1f(u('uTemp'), 0.45)
    gl.uniform1f(u('uDoppler'), 1)
    gl.uniform1f(u('uFondo'), 1)

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const touch = window.matchMedia('(pointer: coarse)').matches
    const minFrameMs = touch ? 33 : 0 // ~30 fps on phones
    let steps = touch ? STEPS_TOUCH : STEPS_DESKTOP
    let dpr = touch ? 0.75 : Math.min(window.devicePixelRatio || 1, 1.25)
    let raf = 0
    let inView = true
    let stopped = false // adaptive fallback gave up: keep the last frame
    let last = 0 // last drawn frame time
    let prev = 0 // last RAF callback time (for frame-time sampling)
    let yaw = 0
    let level = 0 // 0 full budget, 1 degraded
    let sampled = 0
    let sampleMs = 0

    const resize = () => {
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr))
      const h = Math.max(1, Math.round(canvas.clientHeight * dpr))
      const phone = canvas.clientWidth < PHONE_MAX_W
      const view = phone ? PHONE : DESKTOP
      gl.uniform2f(uCenter, view.cx, view.cy)
      gl.uniform1f(uZoom, view.zoom)
      if (canvas.width === w && canvas.height === h) return
      canvas.width = w
      canvas.height = h
      gl.viewport(0, 0, w, h)
      gl.uniform2f(uRes, w, h)
    }
    const draw = (seconds) => {
      gl.uniform1f(uTime, seconds)
      gl.uniform1f(uYaw, yaw)
      gl.uniform1f(uPasos, steps)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    }
    // Judge performance on RAF-to-RAF time, which grows when draws are slow.
    const judge = (dtMs) => {
      if (dtMs > 250) return // tab was backgrounded or throttled, not a GPU signal
      sampled += 1
      sampleMs += dtMs
      if (sampled < SAMPLE_FRAMES) return
      const slow = sampleMs / sampled > SLOW_FRAME_MS
      sampled = 0
      sampleMs = 0
      if (!slow) return
      if (level === 0) {
        level = 1
        steps = Math.max(1, Math.floor(steps / 2))
        dpr = FALLBACK_DPR
        resize()
      } else {
        stopped = true
        cancelAnimationFrame(raf)
      }
    }
    const frame = (t) => {
      raf = requestAnimationFrame(frame)
      const dtMs = prev ? t - prev : 0
      prev = t
      if (document.hidden || !inView) return
      if (dtMs) judge(dtMs)
      if (stopped || t - last < minFrameMs) return
      yaw += Math.min(t - last, 100) * 0.001 * ORBIT_RATE
      last = t
      draw(t * 0.001)
    }
    const onLost = (e) => {
      e.preventDefault()
      cancelAnimationFrame(raf)
      removeCanvas()
      setMode('off')
    }
    const still = () => {
      yaw = 0
      draw(STILL_TIME)
    }

    resize()
    if (reduced) still()
    else raf = requestAnimationFrame(frame)
    canvas.addEventListener('webglcontextlost', onLost)
    // A resize clears the drawing buffer, so repaint the frozen frame.
    const ro =
      'ResizeObserver' in window
        ? new ResizeObserver(() => {
            resize()
            if (reduced) still()
            else if (stopped) draw(last * 0.001)
          })
        : null
    ro?.observe(canvas)
    const io =
      'IntersectionObserver' in window
        ? new IntersectionObserver((en) => { inView = en[0].isIntersecting }, { threshold: 0 })
        : null
    io?.observe(canvas)
    const show = requestAnimationFrame(() => {
      canvas.style.opacity = 'var(--iridescence-opacity)'
      setMode('on')
    })

    return () => {
      cancelAnimationFrame(raf)
      cancelAnimationFrame(show)
      canvas.removeEventListener('webglcontextlost', onLost)
      ro?.disconnect()
      io?.disconnect()
      gl.getExtension('WEBGL_lose_context')?.loseContext()
      removeCanvas()
    }
  }, [night])

  return (
    <div aria-hidden="true" className={cn('grain pointer-events-none absolute inset-0 -z-10 overflow-hidden', className)}>
      <div ref={hostRef} className="absolute inset-0" />
      {(!night || mode === 'off') && (
        <div className="absolute left-[78%] top-1/2 h-[170%] w-[60%] -translate-x-1/2 -translate-y-1/2 bg-[radial-gradient(closest-side,rgba(255,170,80,0.16),transparent)] sm:left-[72%] sm:w-[40%]" />
      )}
    </div>
  )
}
