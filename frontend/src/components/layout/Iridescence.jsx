import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * The redesign's one atmospheric effect (Signal design system; ported from the
 * template's hero shader in frontend/template/redesign-template.html): an
 * iridescent WebGL field tinted to the ink blue, screen-blended and masked to
 * an ellipse so it reads as a glow, not a picture. Used ONLY behind the top of
 * Home — every other page stays still (surface brief: "signature moments").
 *
 * Budget rules, because this is the phone's launch screen:
 *  - DPR capped (1 on touch devices, 1.5 otherwise) and ~30 fps on touch;
 *  - pauses while the tab is hidden or the canvas is off-screen;
 *  - one still frame under prefers-reduced-motion;
 *  - no WebGL, a failed compile or a lost context → `off`, and the CSS radial
 *    glow below stands in. Both paths are kept, as the template asks.
 * Everything (RAF, observers, listeners, the GL context) is torn down on
 * unmount so route changes never leak a render loop.
 */

const VERT =
  'attribute vec2 uv;attribute vec2 position;varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position,0,1);}'
const FRAG = `precision highp float;
uniform float uTime;uniform vec3 uColor;uniform vec3 uResolution;uniform vec2 uMouse;uniform float uAmplitude;uniform float uSpeed;
varying vec2 vUv;
void main(){
  float mr=min(uResolution.x,uResolution.y);
  vec2 uv=(vUv.xy*2.0-1.0)*uResolution.xy/mr;
  uv+=(uMouse-vec2(0.5))*uAmplitude;
  float d=-uTime*0.5*uSpeed;float a=0.0;
  for(float i=0.0;i<8.0;++i){a+=cos(i-d-a*uv.x);d+=sin(uv.y*i+a);}
  d+=uTime*0.5*uSpeed;
  vec3 col=vec3(cos(uv*vec2(d,a))*0.6+0.4,cos(a+d)*0.5+0.5);
  col=cos(col*cos(vec3(d,a,2.5))*0.5+0.5)*uColor;
  gl_FragColor=vec4(col,1.0);
}`

// The shader's tint can't read CSS tokens; this is --signal-deep's ink blue
// in 0–1 RGB. Retheme it by hand alongside --primary / --signal-deep.
const TINT = [0.3, 0.42, 0.82]

const MASK = 'radial-gradient(55% 52% at 58% 46%, #000 0%, rgba(0,0,0,0.6) 46%, transparent 76%)'

export default function Iridescence({ className }) {
  const canvasRef = useRef(null)
  const [mode, setMode] = useState('pending') // pending → on | off

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    let gl = null
    try {
      const opts = { alpha: true, antialias: false, depth: false, stencil: false, powerPreference: 'low-power' }
      gl = canvas.getContext('webgl', opts) || canvas.getContext('experimental-webgl', opts)
    } catch {
      gl = null
    }
    if (!gl) {
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
      setMode('off')
      return undefined
    }
    gl.useProgram(prog)

    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 0, 0, 3, -1, 2, 0, -1, 3, 0, 2]), gl.STATIC_DRAW)
    const aPos = gl.getAttribLocation(prog, 'position')
    const aUv = gl.getAttribLocation(prog, 'uv')
    gl.enableVertexAttribArray(aPos)
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 16, 0)
    gl.enableVertexAttribArray(aUv)
    gl.vertexAttribPointer(aUv, 2, gl.FLOAT, false, 16, 8)

    const uTime = gl.getUniformLocation(prog, 'uTime')
    const uRes = gl.getUniformLocation(prog, 'uResolution')
    const uMouse = gl.getUniformLocation(prog, 'uMouse')
    gl.uniform3f(gl.getUniformLocation(prog, 'uColor'), ...TINT)
    gl.uniform1f(gl.getUniformLocation(prog, 'uAmplitude'), 0.08)
    gl.uniform1f(gl.getUniformLocation(prog, 'uSpeed'), 0.32)

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const touch = window.matchMedia('(pointer: coarse)').matches
    const dpr = Math.min(window.devicePixelRatio || 1, touch ? 1 : 1.5)
    const minFrameMs = touch ? 33 : 0 // ~30 fps on phones
    const mouse = { x: 0.5, y: 0.5 }
    const smooth = { x: 0.5, y: 0.5 }
    let raf = 0
    let inView = true
    let last = 0

    const resize = () => {
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr))
      const h = Math.max(1, Math.round(canvas.clientHeight * dpr))
      if (canvas.width === w && canvas.height === h) return
      canvas.width = w
      canvas.height = h
      gl.viewport(0, 0, w, h)
      gl.uniform3f(uRes, w, h, w / h)
    }
    const draw = (t) => {
      smooth.x += (mouse.x - smooth.x) * 0.04
      smooth.y += (mouse.y - smooth.y) * 0.04
      gl.uniform2f(uMouse, smooth.x, smooth.y)
      gl.uniform1f(uTime, reduced ? 8.4 : t * 0.001)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    }
    const frame = (t) => {
      raf = requestAnimationFrame(frame)
      if (document.hidden || !inView || t - last < minFrameMs) return
      last = t
      draw(t)
    }
    const onMove = (e) => {
      const r = canvas.getBoundingClientRect()
      mouse.x = (e.clientX - r.left) / r.width
      mouse.y = 1 - (e.clientY - r.top) / r.height
    }
    const onLost = (e) => {
      e.preventDefault()
      cancelAnimationFrame(raf)
      setMode('off')
    }

    resize()
    if (reduced) draw(0)
    else raf = requestAnimationFrame(frame)
    window.addEventListener('mousemove', onMove, { passive: true })
    canvas.addEventListener('webglcontextlost', onLost)
    const ro = 'ResizeObserver' in window ? new ResizeObserver(() => { resize(); if (reduced) draw(0) }) : null
    ro?.observe(canvas)
    const io =
      'IntersectionObserver' in window
        ? new IntersectionObserver((en) => { inView = en[0].isIntersecting }, { threshold: 0 })
        : null
    io?.observe(canvas)
    const show = requestAnimationFrame(() => setMode('on'))

    return () => {
      cancelAnimationFrame(raf)
      cancelAnimationFrame(show)
      window.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('webglcontextlost', onLost)
      ro?.disconnect()
      io?.disconnect()
      gl.getExtension('WEBGL_lose_context')?.loseContext()
    }
  }, [])

  return (
    <div aria-hidden="true" className={cn('grain pointer-events-none absolute inset-0 -z-10 overflow-hidden', className)}>
      {mode === 'off' ? (
        <div className="absolute right-[-10%] top-0 h-full w-[70%] bg-[radial-gradient(40%_40%_at_55%_45%,rgba(43,86,201,0.45),transparent_70%)] blur-[30px]" />
      ) : (
        <canvas
          ref={canvasRef}
          className={cn(
            'absolute right-[-35%] top-[-60%] h-[220%] w-[min(900px,140vw)] transition-opacity duration-[2400ms] ease-signal md:right-[-8%]',
            // Blend + strength are theme tokens: screen lights the ink in dark,
            // multiply tints the paper in light (screen on white is invisible).
            mode === 'on' ? 'opacity-[var(--iridescence-opacity)] [mix-blend-mode:var(--iridescence-blend)]' : 'opacity-0 [mix-blend-mode:var(--iridescence-blend)]'
          )}
          style={{ WebkitMaskImage: MASK, maskImage: MASK }}
        />
      )}
    </div>
  )
}
