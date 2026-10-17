import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * The shared PageHeader backdrop: a calm Maasai savanna at the horizon, drawn in
 * SVG + CSS (no WebGL, no dependencies). It replaces the old black-hole shader.
 *
 * Credit: recomposed from INSTALANDING.AI "Maasai-Inspired Event Landing Page"
 * (MIT, frontend/template/maasai-template.html), whose hero recreates the
 * "Maasai-Inspired Event Hero Banner Concept" from the Rive Marketplace in plain
 * SVG and CSS. The warrior and bird symbols, cloud/ridge/ground paths and the
 * adumu leap are the template's; keep this credit.
 *
 * Recomposition, not a crop. The template is a fixed 1672x940 stage; the band is
 * a very wide strip (about 100-120px tall on phones, 150-180px on desktop), so
 * the scene is rebuilt in layers sized to the band rather than the stage:
 *  1. sky: a CSS gradient, top to horizon;
 *  2. sun: a disc with a radial glow, low behind the ridge at left 74%, about 70%
 *     of the band height across, with the template's slow pulse;
 *  3. clouds: three of the template's cloud paths drifting in a strip up top;
 *  4. landscape: one full-width SVG on the bottom ~48% (the stage's lower part,
 *     stretched with preserveAspectRatio="none"): two ridges and the ground.
 *     Haze, pebbles and grass strokes are dropped as noise at this size. The
 *     acacias are separate small SVGs, because a stretched SVG would squash them;
 *  5. warriors: buttons standing on the ground line, heights in % of the band.
 *     The tallest front warrior is 58%; the others keep the template's relative
 *     sizes. Four from `sm:` up, only the two middle ones on phones, same order
 *     and mirroring as the template (the inner svg is flipped, not the button);
 *  6. flock: a few birds crossing the sky slowly, with the wing flap;
 *  7. scrim: a left-to-right fade of --background so the title and meta line keep
 *     their contrast. Dropped from the template: the MAASAI word, reeds, grass
 *     clumps, grain, parallax and the frieze.
 *
 * Theming is custom properties only: every colour is a --sv-* token in index.css,
 * defined for the dark ("night") and light ("dusk") themes, so a theme toggle
 * repaints with no React state. The warriors keep their own symbol fills (shuka
 * red etc.); the dark theme only dims them with --sv-warrior-filter. Symbol and
 * gradient ids are sv- prefixed so they cannot clash with anything else in the page.
 *
 * Motion is calm; this is an app tool, not a landing page. The CSS loops (sun,
 * clouds, flock, wing flap) live in index.css as sv-* keyframes. The adumu leap
 * (Web Animations, ported from the template with the lift scaled down so the jump
 * stays inside the clipped band) plays in two cases only: once per page load, the
 * visible warriors leap left to right 170ms apart about 900ms after the first
 * mount (module-level flag, so route changes do not replay it), and when a
 * warrior is clicked. There are no ambient or random leaps. Under
 * prefers-reduced-motion the loops and the load leap are off; a click still plays
 * one leap. The warriors are buttons with tabIndex -1 inside an aria-hidden,
 * pointer-events-none root: a decorative easter egg that stays out of the tab
 * order. Timers are cleared on unmount.
 */

// Module-level so the greeting plays once per page load, not on every route change.
let greeted = false

const GREET_DELAY_MS = 900
const GREET_STAGGER_MS = 170
// Template lift is -62% of the warrior; the band clips overflow, so keep the jump inside it.
const LIFT_PCT = -38

/** The adumu: crouch, straight-legged spring, hang, land (ported from the template). */
function leap(body, shadow, lift, dur) {
  dur = dur || 1150
  const a = body.animate(
    [
      { transform: 'translateY(0) scaleY(1)', easing: 'ease-out' },
      { transform: 'translateY(2%) scaleY(.93)', offset: 0.14, easing: 'cubic-bezier(.15,.8,.35,1)' },
      { transform: 'translateY(' + lift + '%) scaleY(1.03)', offset: 0.42, easing: 'linear' },
      { transform: 'translateY(' + (lift - 3) + '%) scaleY(1)', offset: 0.54, easing: 'cubic-bezier(.55,0,.85,.4)' },
      { transform: 'translateY(1.5%) scaleY(.95)', offset: 0.86, easing: 'ease-out' },
      { transform: 'translateY(0) scaleY(1)' },
    ],
    { duration: dur },
  )
  if (shadow) {
    shadow.animate(
      [
        { transform: 'scale(1)', opacity: 1 },
        { transform: 'scale(1.1)', opacity: 1, offset: 0.14 },
        { transform: 'scale(.45)', opacity: 0.35, offset: 0.45 },
        { transform: 'scale(.42)', opacity: 0.3, offset: 0.54 },
        { transform: 'scale(1.05)', opacity: 1, offset: 0.86 },
        { transform: 'scale(1)', opacity: 1 },
      ],
      { duration: dur },
    )
  }
  return a
}

function jump(w) {
  if (w.dataset.busy) return
  w.dataset.busy = '1'
  const body = w.querySelector('[data-sv-body]')
  const shadow = w.querySelector('[data-sv-shadow]')
  if (!body || !body.animate) {
    delete w.dataset.busy
    return
  }
  const lift = LIFT_PCT * parseFloat(w.dataset.lift || '1')
  leap(body, shadow, lift).onfinish = () => {
    delete w.dataset.busy
  }
}

// Heights are % of the band: front 865/250 and side 610/105 at the template's
// relative widths (.w-l/.w-s/.w-b/.w-r), scaled so the tallest front (w-b) is 58%.
// Only the desktop band positions them by left-%; phones use SavannaWarriorsInline.
const WARRIORS = [
  { id: 'l', label: 'first', symbol: 'sv-w-side', box: '105 / 610', height: 64, bottom: 9, lift: 1.08, flip: false, cls: 'hidden sm:block left-[54%]' },
  { id: 's', label: 'second', symbol: 'sv-w-front', box: '250 / 865', height: 52, bottom: 11, lift: 0.72, flip: false, cls: 'hidden sm:block left-[58.5%]' },
  { id: 'b', label: 'third', symbol: 'sv-w-front', box: '250 / 865', height: 58, bottom: 10, lift: 0.9, flip: true, cls: 'hidden sm:block left-[63%]' },
  { id: 'r', label: 'fourth', symbol: 'sv-w-side', box: '105 / 610', height: 65, bottom: 8, lift: 1.1, flip: true, cls: 'hidden sm:block left-[68%]' },
]

const BIRDS = [
  { left: '0%', top: '22%', d: '-.1s', delay: '0s' },
  { left: '21%', top: '4%', d: '-.3s', delay: '-.6s' },
  { left: '43%', top: '-4%', d: '-.18s', delay: '-1.2s' },
  { left: '65%', top: '-4%', d: '-.36s', delay: '-.3s' },
  { left: '11%', top: '46%', d: '-.24s', delay: '-1.6s' },
  { left: '33%', top: '62%', d: '-.06s', delay: '-.9s' },
]

const ACACIAS = [
  { left: '80%', bottom: '17%', height: '17%' },
  { left: '87%', bottom: '14%', height: '12%' },
  { left: '93%', bottom: '16%', height: '15%' },
]

function Warrior({ w, className, style }) {
  return (
    <button
      type="button"
      tabIndex={-1}
      data-sv-warrior
      data-lift={w.lift}
      aria-label={`Make the ${w.label} warrior jump`}
      onClick={(e) => jump(e.currentTarget)}
      className={cn(
        'pointer-events-auto absolute cursor-pointer border-0 bg-transparent p-0 [-webkit-tap-highlight-color:transparent]',
        className,
      )}
      style={{ aspectRatio: w.box, ...style }}
    >
      <span
        data-sv-shadow
        className="absolute inset-x-[12%] -bottom-[1.2%] h-[4%] rounded-full blur-[2px]"
        style={{ background: 'var(--sv-shadow)' }}
      />
      <span data-sv-body className="block h-full w-full origin-bottom">
        <svg
          className="block h-full w-full overflow-visible"
          viewBox={`0 0 ${w.box.replace(' / ', ' ')}`}
          style={{ transform: w.flip ? 'scaleX(-1)' : undefined, filter: 'var(--sv-warrior-filter)' }}
        >
          <use href={`#${w.symbol}`} />
        </svg>
      </span>
    </button>
  )
}

/**
 * Phones: the two middle warriors, placed inline in the PageHeader flex row
 * between the title and the actions so the action button never hides them.
 * -mb-4 cancels the band's phone bottom padding so they stand on the ground
 * line; heights are px (tallest 56px) since the box has no band-relative height.
 */
export function SavannaWarriorsInline() {
  const boxRef = useRef(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const el = boxRef.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Never show a clipped warrior: the pair if both fit whole (plus breathing
  // room), else w-b alone if it fits, else nothing. Width = height x aspect ratio.
  const GAP = 4
  const ROOM = 8
  const s = { ...WARRIORS[1], px: 48 }
  const b = { ...WARRIORS[2], px: 56 }
  const wOf = (w) => (w.px * 250) / 865
  let pair = []
  if (width >= wOf(s) + GAP + wOf(b) + ROOM) pair = [s, b]
  else if (width >= wOf(b) + ROOM) pair = [b]

  return (
    <div ref={boxRef} aria-hidden="true" className="pointer-events-none relative -mb-4 min-w-[44px] flex-1 self-stretch overflow-hidden sm:hidden">
      <div className="absolute inset-x-0 bottom-[10px] flex items-end justify-center gap-1">
        {pair.map((w) => (
          <Warrior key={w.id} w={w} className="relative" style={{ height: w.px }} />
        ))}
      </div>
    </div>
  )
}

export default function SavannaHeader({ className }) {
  const rootRef = useRef(null)

  useEffect(() => {
    if (greeted) return undefined
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined
    const timers = []
    timers.push(
      setTimeout(() => {
        greeted = true
        const band = rootRef.current?.parentElement
        const all = band?.querySelectorAll('[data-sv-warrior]') || []
        // The phone hides two warriors with display:none; they have no box.
        const visible = Array.from(all).filter((w) => w.getClientRects().length > 0)
        visible.forEach((w, i) => timers.push(setTimeout(() => jump(w), i * GREET_STAGGER_MS)))
      }, GREET_DELAY_MS),
    )
    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <div ref={rootRef} aria-hidden="true" className={cn('pointer-events-none absolute inset-0 -z-10 overflow-hidden', className)}>
      {/* Symbol sprite. A <use> inside its own <svg> needs viewBox "0 0 w h". */}
      <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
        <defs>
          <symbol id="sv-w-front" viewBox="320 55 250 865">
          <path d="M343 60 L357 120 L343 148 L330 120Z" fill="#1a1514"/>
          <rect x="339.5" y="140" width="7" height="776" fill="#1d1918"/>
          <path d="M384 728 L412 756 L410 836 L380 838Z" fill="#4a1206"/>
          <path d="M494 735 L522 788 L497 818Z" fill="#4a1206"/>
          <path d="M410 750 L442 760 L436 893 L420 893Z" fill="#0b0807"/>
          <path d="M468 725 L500 732 L490 893 L473 893Z" fill="#0b0807"/>
          <path d="M420 890 L436 892 L436 910 L406 916 L407 906Z" fill="#0b0807"/>
          <path d="M472 890 L490 892 L503 905 L503 916 L470 915Z" fill="#0b0807"/>
          <path d="M438 360 L462 360 L460 392 L448 404 L436 392Z" fill="#22140f"/>
          <ellipse cx="450" cy="343" rx="21" ry="26" fill="#22140f"/>
          <path d="M469 348 Q479 355 472 369 Q466 360 469 348Z" fill="#140b08"/>
          <path d="M496 412 L518 420 L528 450 L540 500 L552 542 L556 605 L566 640 L556 652 L548 656 L546 628 L544 612 L530 552 L516 500 L504 462Z" fill="#1d130f"/>
          <path d="M380 418 L402 424 L398 470 L394 510 L388 538 L374 534 L354 508 L338 502 L330 492 L332 478 L348 474 L356 492 L374 508 L376 470Z" fill="#22140f"/>
          <path d="M388 412 L432 390 L448 404 L466 390 L492 406 L514 420 L500 470 L490 520 L410 522 L400 470Z" fill="#15100d"/>
          <path d="M400 410 L420 400 L448 432 L470 398 L492 408 L470 432 L436 460Z" fill="#a9441b"/>
          <path d="M420 400 L432 390 L448 410 L466 390 L470 398 L448 432Z" fill="#15100d"/>
          <path d="M432 390 L448 410 L466 390" stroke="#fff" strokeWidth="2" fill="none" strokeLinejoin="round"/>
          <path d="M436 460 L470 492" stroke="#2c1d17" strokeWidth="2"/>
          <path d="M388 412 L412 505" stroke="#fff" strokeWidth="1.6"/>
          <path d="M410 504 L468 490 L484 522 L410 522Z" fill="#7a2410"/>
          <path d="M408 522 L484 522 L495 568 L446 548 L408 530Z" fill="#15100d"/>
          <path d="M408 530 L446 548 L430 780 L354 708Z" fill="#15100d"/>
          <path d="M446 548 L495 568 L530 785 L438 660Z" fill="#a9441b"/>
          <path d="M438 660 L492 730 L452 855 L430 780Z" fill="#3d1f18"/>
          <path d="M354 708 L430 780 L446 548 L495 568" stroke="#fff" strokeWidth="3" fill="none" strokeLinejoin="round"/>
          </symbol>
          <symbol id="sv-w-side" viewBox="345 155 105 610">
          <path d="M437 162 L445 195 L437 215 L429 195Z" fill="#141111"/>
          <path d="M435 205 L440 205 L434 680 L429 680Z" fill="#1b1716"/>
          <path d="M431 672 L439 690 L432 727 L424 690Z" fill="#141111"/>
          <path d="M388 684 L404 684 L398 728 L420 739 L418 743 L392 740 L386 732Z" fill="#0d0a09"/>
          <path d="M374 684 L394 684 L384 742 L406 754 L405 758 L366 757 L370 744Z" fill="#0b0807"/>
          <path d="M366 505 L404 505 L424 620 L428 688 L356 688 L360 590Z" fill="#6b2a10"/>
          <path d="M366 505 L382 505 L377 688 L356 688 L360 590Z" fill="#58220c"/>
          <path d="M404 505 L418 560 L438 626 L424 638 L410 580Z" fill="#a5562e"/>
          <path d="M418 560 L438 626" stroke="#f3e6da" strokeWidth="1.4"/>
          <path d="M370 410 L400 410 L407 452 L404 522 L368 526 L352 460 L352 432Z" fill="#17110e"/>
          <path d="M378 410 L400 410 L407 452 L382 494 L376 476 L394 444Z" fill="#a3542d"/>
          <path d="M394 444 L407 452 L382 494 L376 476Z" fill="#b97a54"/>
          <path d="M378 411 L404 449" stroke="#f5e9dc" strokeWidth="1.6"/>
          <path d="M386 396 L398 396 L401 414 L384 414Z" fill="#241712"/>
          <path d="M378 380 Q378 364 393 364 Q408 366 408 386 Q408 400 402 404 L394 406 Q382 404 378 392Z" fill="#2c1f19"/>
          <path d="M354 432 L374 436 L378 470 L380 496 L364 504 L358 470Z" fill="#241712"/>
          <path d="M368 494 L408 484 L428 462 L440 464 L438 476 L414 494 L374 510Z" fill="#241712"/>
          <path d="M357 464 L377 466" stroke="#c4672f" strokeWidth="3"/>
          <path d="M359 471 L378 473" stroke="#f0d9c4" strokeWidth="1.5"/>
          <path d="M405 486 L411 495" stroke="#c4672f" strokeWidth="3"/>
          <ellipse cx="434" cy="468" rx="7" ry="8" fill="#241712"/>
          </symbol>
          <symbol id="sv-bird" viewBox="270 470 480 280">
          <path className="sv-wing" d="M404 560 L494 560 L548 582 Q584 598 596 614 L566 640 Q562 668 538 694 L478 732 Q456 676 418 628 Q396 600 410 578Z"/>
          <path d="M278 548 L330 524 Q345 504 368 506 L520 508 Q600 512 742 545 Q640 552 560 576 Q480 588 400 582 Q350 572 336 552Z"/>
          <path className="sv-wing" d="M418 556 L508 556 L560 575 Q600 588 615 603 L586 632 Q585 660 560 690 L505 726 Q480 670 430 620 Q408 598 425 575Z"/>
          </symbol>
          <symbol id="sv-acacia" viewBox="-56 -74 112 76">
            <path d="M-2 0 L-1 -30 L-16 -48 L-14 -49 L0 -34 L12 -52 L14 -51 L2 -32 L2 0Z" />
            <path d="M-50 -48 Q-34 -62 -8 -58 Q8 -66 32 -60 Q50 -56 56 -48 Q28 -44 0 -46 Q-24 -44 -50 -48Z" />
            <path d="M-32 -58 Q-14 -70 10 -66 Q26 -68 38 -60 Q8 -56 -32 -58Z" />
          </symbol>
        </defs>
      </svg>

      {/* 1. Sky */}
      <div
        className="absolute inset-0"
        style={{ background: 'linear-gradient(180deg, var(--sv-sky-top) 0%, var(--sv-sky-mid) 50%, var(--sv-sky-horizon) 100%)' }}
      />

      {/* 2. Sun: glow, then disc, both low behind the ridge */}
      <div
        className="absolute aspect-square rounded-full"
        style={{
          left: '74%',
          top: '54%',
          height: '190%',
          transform: 'translate(-50%, -50%)',
          background: 'radial-gradient(circle, var(--sv-sun-glow) 0%, transparent 62%)',
        }}
      />
      <div
        className="sv-sun absolute aspect-square rounded-full"
        style={{ left: '74%', top: '54%', height: '70%', transform: 'translate(-50%, -50%)', background: 'var(--sv-sun)' }}
      />

      {/* 3. Clouds: the template's cloud paths in a strip across the upper half */}
      <svg
        className="absolute left-0 top-[6%] h-[40%] w-full overflow-visible"
        viewBox="560 150 1100 200"
        preserveAspectRatio="none"
      >
        <g className="sv-cloud" style={{ fill: 'var(--sv-cloud)', opacity: 'var(--sv-cloud-opacity)' }}>
          <path d="M1260 236 Q1300 214 1350 226 Q1390 206 1440 222 Q1500 210 1540 232 Q1600 230 1630 246 L1250 250Z" />
          <path d="M1380 288 Q1420 272 1470 282 Q1520 270 1570 286 L1372 292Z" />
        </g>
        <g className="sv-cloud sv-cloud-b" style={{ fill: 'var(--sv-cloud)', opacity: 'var(--sv-cloud-opacity)' }}>
          <path d="M600 168 Q680 150 760 164 Q840 152 930 170 L590 174Z" />
        </g>
      </svg>

      {/* 6. Flock (sits behind the landscape, in the sky) */}
      <div className="sv-flock absolute left-[50%] top-[10%] aspect-[200/90] w-[9%]">
        {BIRDS.map((b) => (
          <svg
            key={b.left + b.top}
            className="sv-bird absolute w-[15%] overflow-visible"
            viewBox="0 0 480 280"
            style={{ left: b.left, top: b.top, '--d': b.d, animationDelay: b.delay, fill: 'var(--sv-bird)' }}
          >
            <use href="#sv-bird" />
          </svg>
        ))}
      </div>

      {/* 4. Landscape: stage y 200 to 940, stretched to the band's bottom half */}
      <svg
        className="absolute bottom-0 left-0 h-[48%] w-full"
        viewBox="0 200 1672 740"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="sv-ground-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" style={{ stopColor: 'var(--sv-ground-top)' }} />
            <stop offset="1" style={{ stopColor: 'var(--sv-ground-bottom)' }} />
          </linearGradient>
        </defs>
        <path
          d="M880 540 L1000 480 L1120 500 L1250 440 L1360 392 L1420 352 L1470 362 L1560 404 L1672 384 L1672 700 L880 700Z"
          style={{ fill: 'var(--sv-ridge-far)' }}
        />
        <path
          d="M-20 340 L40 312 L90 300 L150 290 L210 262 L300 220 L380 166 L470 128 L515 112 L548 132 L580 190 L640 232 L700 318 L790 380 L880 440 L980 484 L1060 524 L1110 562 L1110 720 L-20 720Z"
          style={{ fill: 'var(--sv-ridge-far)' }}
        />
        <path
          d="M1180 700 L1300 590 L1420 500 L1520 448 L1600 418 L1672 404 L1672 720 L1180 720Z"
          style={{ fill: 'var(--sv-ridge-near)' }}
        />
        <path
          d="M0 590 Q210 548 420 586 T 840 600 T 1260 606 T 1672 592 L1672 720 L0 720Z"
          style={{ fill: 'var(--sv-ridge-near)' }}
        />
        <path d="M0 668 Q400 652 836 660 T 1672 656 L1672 940 L0 940Z" fill="url(#sv-ground-grad)" />
      </svg>

      {/* Acacias: right half, on the ground line (separate so they are not squashed) */}
      {ACACIAS.map((t) => (
        <svg
          key={t.left}
          className="absolute aspect-[112/76] overflow-visible"
          viewBox="0 0 112 76"
          style={{ left: t.left, bottom: t.bottom, height: t.height, fill: 'var(--sv-tree)' }}
        >
          <use href="#sv-acacia" />
        </svg>
      ))}

      {/* 5. Warriors */}
      {WARRIORS.map((w) => (
        <Warrior key={w.id} w={w} className={cn(w.cls)} style={{ height: `${w.height}%`, bottom: `${w.bottom}%` }} />
      ))}

      {/* 7. Left scrim: keeps the title and meta line calm */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(90deg, color-mix(in srgb, var(--background) 85%, transparent) 0%, transparent 45%)',
        }}
      />
    </div>
  )
}
