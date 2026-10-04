import { useEffect, useRef, type MutableRefObject, type RefObject } from "react";
import {
  BackSide, NormalBlending, BufferAttribute, BufferGeometry, CatmullRomCurve3, Mesh, PerspectiveCamera, Points, Scene,
  ShaderMaterial, SphereGeometry, Vector3, Vector4, WebGLRenderer,
} from "three";

import { buildStory, CANADA_LON, CARD_CENTER, GLOBE_R, ROAD_POINTS, type Palette, type Rgb } from "./shapes";

/* The scroll story behind the signed-out hero: one WebGL scene, one draw call for the particles.
 * Every particle carries a target position for each of the four shapes (globe, Canada, road, card) as vertex
 * attributes; the vertex shader blends between them from one `uStage` uniform, so the CPU never moves a particle.
 * Cost control, because it sits on the first screen:
 * - Loaded lazily (its own chunk with three.js), after the headline and buttons have painted.
 * - Fewer particles on small screens and on machines with few cores; device pixel ratio capped at 2, and dropped
 *   to 1 if frames get slow.
 * - Stops drawing when the section is off screen or the tab is hidden.
 * - Everything is disposed on unmount. If WebGL cannot start, `onFail` lets the hero fall back to the 2D globe. */

export interface StorySceneProps {
  /** Raw scroll progress through the story, 0 to 1, written by the hero on scroll. The scene eases towards it. */
  progress: MutableRefObject<number>;
  onFail: () => void;
  /** The text the particles must stay clear of: the text column (wide screens: nothing drawn left of its right edge),
   * the captions (tall screens: nothing above their bottom) and the buttons (tall screens: nothing below their top). */
  avoid?: { column: RefObject<HTMLElement>; captions: RefObject<HTMLElement>; actions: RefObject<HTMLElement>; rail: RefObject<HTMLElement> };
}

const FOV = 40;
const STAGES: [number, number][] = [[0, 0], [0.1, 0], [0.3, 1], [0.4, 1], [0.58, 2], [0.76, 2], [0.92, 3], [1, 3]];
const DEG = Math.PI / 180;

const VERT = /* glsl */ `
uniform float uStage, uTime, uRot, uTilt, uScale;
uniform vec4 uAvoid; // in clip space: fade left of x, above y (top), below z (bottom), right of w (the story rail)
attribute vec3 aPosB, aPosC, aPosD, aColA, aColB, aColC, aColD;
attribute vec4 aAlpha, aSize, aRand;
varying vec3 vCol;
varying float vAlpha;

vec3 globe(vec3 p) {
  float c = cos(uRot), s = sin(uRot);
  p = vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z);
  float ct = cos(uTilt), st = sin(uTilt);
  return vec3(p.x, ct * p.y - st * p.z, st * p.y + ct * p.z);
}

void main() {
  float stage = clamp(uStage, 0.0, 3.0);
  float seg = min(floor(stage), 2.0);
  float f = stage - seg;
  vec3 pA = globe(position);
  float facing = mix(0.07, 1.0, smoothstep(-0.35, 0.55, pA.z / ${GLOBE_R.toFixed(2)}));
  vec3 p0, p1, c0, c1; float a0, a1, s0, s1, d;
  if (seg < 0.5) { p0 = pA; p1 = aPosB; c0 = aColA; c1 = aColB; a0 = aAlpha.x * facing; a1 = aAlpha.y; s0 = aSize.x; s1 = aSize.y; d = aRand.x; }
  else if (seg < 1.5) { p0 = aPosB; p1 = aPosC; c0 = aColB; c1 = aColC; a0 = aAlpha.y; a1 = aAlpha.z; s0 = aSize.y; s1 = aSize.z; d = aRand.y; }
  else { p0 = aPosC; p1 = aPosD; c0 = aColC; c1 = aColD; a0 = aAlpha.z; a1 = aAlpha.w; s0 = aSize.z; s1 = aSize.w; d = aRand.z; }
  float k = clamp((f - d * 0.5) / 0.5, 0.0, 1.0);
  k = k * k * (3.0 - 2.0 * k);

  vec3 p = mix(p0, p1, k);
  // break apart in flight: each particle swings out along its own direction and settles again
  float burst = sin(k * 3.14159);
  vec3 dir = normalize(vec3(sin(aRand.w * 127.1), cos(aRand.w * 311.7), sin(aRand.w * 74.7 + 1.0)) + 1e-4);
  p += dir * burst * (0.25 + 0.45 * fract(aRand.w * 13.0));
  p += 0.006 * vec3(sin(uTime * 0.7 + aRand.w * 40.0), cos(uTime * 0.6 + aRand.w * 30.0), sin(uTime * 0.5 + aRand.w * 20.0));

  vCol = mix(c0, c1, k);
  float twinkle = 0.85 + 0.15 * sin(uTime * 1.3 + aRand.w * 60.0);
  vAlpha = mix(a0, a1, k) * twinkle * (1.0 + burst * 0.25);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vAlpha *= smoothstep(1.1, 2.7, -mv.z); // no big blurry dots right in front of the lens
  gl_PointSize = clamp(mix(s0, s1, k) * uScale / max(-mv.z, 0.1), 1.0, 14.0);
  gl_Position = projectionMatrix * mv;
  // keep the text readable: particles fade out softly as they reach the text column or the captions and buttons
  vec2 ndc = gl_Position.xy / max(gl_Position.w, 1e-3);
  vAlpha *= smoothstep(uAvoid.x, uAvoid.x + 0.14, ndc.x) * (1.0 - smoothstep(uAvoid.y - 0.1, uAvoid.y, ndc.y)) * smoothstep(uAvoid.z, uAvoid.z + 0.08, ndc.y) * (1.0 - smoothstep(uAvoid.w - 0.08, uAvoid.w, ndc.x));
}`;

const FRAG = /* glsl */ `
varying vec3 vCol;
varying float vAlpha;
void main() {
  float d = length(gl_PointCoord - 0.5) * 2.0;
  if (d > 1.0) discard;
  float a = smoothstep(1.0, 0.35, d);
  gl_FragColor = vec4(vCol, a * min(vAlpha, 1.0));
}`;

const ATMO_VERT = /* glsl */ `
varying float vDot;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vec3 n = normalize(normalMatrix * normal);
  vDot = dot(n, normalize(-mv.xyz));
  gl_Position = projectionMatrix * mv;
}`;
const ATMO_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
varying float vDot;
void main() {
  float ring = clamp(1.0 - abs(vDot + 0.42) * 2.4, 0.0, 1.0);
  gl_FragColor = vec4(uColor, pow(ring, 2.2) * uOpacity);
}`;

function hex(v: string, fallback: Rgb): Rgb {
  const m = v.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (!m) return fallback;
  const h = m[1].length === 3 ? m[1].split("").map((c) => c + c).join("") : m[1];
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as Rgb;
}
const mix = (a: Rgb, b: Rgb, t: number): Rgb => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const smooth = (a: number, b: number, x: number) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

/** The colours, read from the design tokens at runtime (no hex in components; the fallbacks only cover a missing token). */
function palette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const t = (n: string, d: Rgb) => hex(css.getPropertyValue(n), d);
  const brand = t("--color-brand", [0.65, 0.12, 0.24]), brand700 = t("--color-brand-700", [0.53, 0.09, 0.2]);
  const brand300 = t("--color-brand-300", [0.95, 0.55, 0.61]), ink = t("--color-ink", [0.1, 0.1, 0.14]);
  const teal = t("--color-teal", [0.1, 0.41, 0.36]);
  // on the light page: red and ink for contrast, teal for "back on track"
  return { red: mix(brand, brand700, 0.25), redSoft: mix(brand, brand300, 0.3), ink, teal, tealSoft: teal };
}

function piecewise(keys: [number, number][], p: number) {
  for (let i = 1; i < keys.length; i++) if (p <= keys[i][0]) {
    const [p0, v0] = keys[i - 1], [p1, v1] = keys[i];
    return v0 + ((v1 - v0) * (p - p0)) / Math.max(p1 - p0, 1e-6);
  }
  return keys[keys.length - 1][1];
}

/** Where the camera is, what it looks at, and how far the picture is shifted off-centre (to leave room for the text). */
function cameraPath() {
  const road = new CatmullRomCurve3(ROAD_POINTS.map((p) => new Vector3(...p)), false, "catmullrom", 0.5);
  const card = new Vector3(...CARD_CENTER);
  const onRoad = (t: number) => {
    const p = road.getPointAt(t), tan = road.getTangentAt(t);
    return { pos: p.clone().add(new Vector3(0, 0.62, 0)).addScaledVector(tan, -1.25), look: road.getPointAt(Math.min(1, t + 0.16)).add(new Vector3(0, 0.12, 0)) };
  };
  const keys: { p: number; pos: Vector3; look: Vector3; sx: number; sy: number }[] = [
    { p: 0, pos: new Vector3(0, 0, 5.6), look: new Vector3(0, 0, 0), sx: 0.3, sy: -0.2 },
    { p: 0.1, pos: new Vector3(0, 0, 5.4), look: new Vector3(0, 0, 0), sx: 0.3, sy: -0.2 },
    { p: 0.3, pos: new Vector3(0, -0.05, 4.7), look: new Vector3(0, 0, 0), sx: 0.33, sy: -0.15 },
    { p: 0.4, pos: new Vector3(0, -0.12, 4.4), look: new Vector3(0, -0.02, 0), sx: 0.33, sy: -0.15 },
    { p: 0.5, ...onRoad(0.0), sx: 0.3, sy: -0.12 },
    { p: 0.6, ...onRoad(0.16), sx: 0.24, sy: -0.1 },
    { p: 0.7, ...onRoad(0.36), sx: 0.24, sy: -0.1 },
    { p: 0.8, ...onRoad(0.56), sx: 0.26, sy: -0.12 },
    { p: 0.92, pos: card.clone().add(new Vector3(0, -0.05, 4.7)), look: card.clone(), sx: 0.3, sy: -0.14 },
    { p: 1, pos: card.clone().add(new Vector3(0, -0.05, 4.65)), look: card.clone(), sx: 0.3, sy: -0.14 },
  ];
  const posCurve = new CatmullRomCurve3(keys.map((k) => k.pos), false, "centripetal");
  const lookCurve = new CatmullRomCurve3(keys.map((k) => k.look), false, "centripetal");
  return (p: number, outPos: Vector3, outLook: Vector3) => {
    let i = 0;
    while (i < keys.length - 2 && p > keys[i + 1].p) i++;
    const f = Math.min(1, Math.max(0, (p - keys[i].p) / (keys[i + 1].p - keys[i].p)));
    const u = (i + f) / (keys.length - 1);
    posCurve.getPoint(u, outPos); lookCurve.getPoint(u, outLook);
    return { sx: keys[i].sx + (keys[i + 1].sx - keys[i].sx) * f, sy: keys[i].sy + (keys[i + 1].sy - keys[i].sy) * f };
  };
}

export default function StoryScene({ progress, onFail, avoid }: StorySceneProps) {
  const box = useRef<HTMLDivElement>(null);
  const failRef = useRef(onFail);
  failRef.current = onFail;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ antialias: false, alpha: true, powerPreference: "high-performance" });
    } catch {
      failRef.current();
      return;
    }
    const canvas = renderer.domElement;
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.display = "block";
    el.appendChild(canvas);

    const small = Math.min(window.innerWidth, window.innerHeight) < 700 || (navigator.hardwareConcurrency || 8) <= 4;
    const count = small ? 9000 : 15000;
    let maxDpr = Math.min(window.devicePixelRatio || 1, 2);

    const story = buildStory(count, palette());
    const geom = new BufferGeometry();
    geom.setAttribute("position", new BufferAttribute(story.pos[0], 3));
    geom.setAttribute("aPosB", new BufferAttribute(story.pos[1], 3));
    geom.setAttribute("aPosC", new BufferAttribute(story.pos[2], 3));
    geom.setAttribute("aPosD", new BufferAttribute(story.pos[3], 3));
    ["aColA", "aColB", "aColC", "aColD"].forEach((n, i) => geom.setAttribute(n, new BufferAttribute(story.col[i], 3)));
    geom.setAttribute("aAlpha", new BufferAttribute(story.alpha, 4));
    geom.setAttribute("aSize", new BufferAttribute(story.size, 4));
    geom.setAttribute("aRand", new BufferAttribute(story.rand, 4));
    const uniforms = { uStage: { value: 0 }, uTime: { value: 0 }, uRot: { value: 0 }, uTilt: { value: 0 }, uScale: { value: 600 }, uAvoid: { value: new Vector4(-10, 10, -10, 10) } };
    const mat = new ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, depthTest: false, blending: NormalBlending });
    const points = new Points(geom, mat);
    points.frustumCulled = false;

    const pal = palette();
    const atmoGeom = new SphereGeometry(GLOBE_R * 1.16, 48, 32);
    const atmoMat = new ShaderMaterial({
      uniforms: { uColor: { value: pal.redSoft }, uOpacity: { value: 0.12 } },
      vertexShader: ATMO_VERT, fragmentShader: ATMO_FRAG, side: BackSide, transparent: true, depthWrite: false, blending: NormalBlending,
    });
    const atmo = new Mesh(atmoGeom, atmoMat);

    const scene = new Scene();
    scene.add(atmo, points);
    const camera = new PerspectiveCamera(FOV, 1, 0.05, 60);
    const path = cameraPath();
    const camPos = new Vector3(), camLook = new Vector3();

    let frames = 0, w = 0, h = 0, raf = 0, visible = true, last = 0, eased = progress.current, spin = -CANADA_LON * DEG - 0.9, slowFrames = 0;
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

    /** Where the text is, in clip space. Wide screens (the lg layout): the column's right edge. Tall: captions and buttons. */
    const measure = () => {
      const r = el.getBoundingClientRect();
      if (!avoid || !r.width || !r.height) return;
      const nx = (x: number) => ((x - r.left) / r.width) * 2 - 1, ny = (y: number) => 1 - ((y - r.top) / r.height) * 2;
      const col = avoid.column.current, cap = avoid.captions.current, act = avoid.actions.current, rail = avoid.rail.current;
      if (window.innerWidth >= 1024) {
        // the right edge of the text actually shown (the column box is wider than most lines)
        let right = -Infinity;
        const range = document.createRange();
        for (const n of cap?.querySelectorAll(".is-on > *") ?? []) { range.selectNodeContents(n); right = Math.max(right, range.getBoundingClientRect().right); }
        for (const n of act?.children ?? []) right = Math.max(right, n.getBoundingClientRect().right);
        if (!Number.isFinite(right) && col) right = col.getBoundingClientRect().right;
        uniforms.uAvoid.value.set(Number.isFinite(right) ? nx(right + 24) : -10, 10, -10, rail ? nx(rail.getBoundingClientRect().left - 12) : 10);
      }
      else uniforms.uAvoid.value.set(-10, cap ? ny(cap.getBoundingClientRect().bottom + 12) : 10, act ? ny(act.getBoundingClientRect().top - 8) : -10, 10);
    };

    const resize = () => {
      measure();
      w = el.clientWidth; h = el.clientHeight;
      if (!w || !h) return;
      renderer.setPixelRatio(maxDpr);
      renderer.setSize(w, h, false);
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
      camera.aspect = w / h;
      uniforms.uScale.value = ((h * maxDpr) / (2 * Math.tan((FOV * DEG) / 2))) * (w < 700 ? 1.45 : 1.15); // solid dots on cream read smaller than glows; small screens a little larger again
    };

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min((now - (last || now)) / 1000, 0.1);
      last = now;
      if (dt > 0.045) slowFrames++; else slowFrames = Math.max(0, slowFrames - 1);
      if (slowFrames > 40 && maxDpr > 1) { maxDpr = 1; slowFrames = 0; resize(); } // slow machine: fewer pixels

      eased += (progress.current - eased) * (1 - Math.exp(-dt * 5));
      const p = eased;
      uniforms.uTime.value = now / 1000;
      uniforms.uStage.value = piecewise(STAGES, p);
      if (++frames % 20 === 0) measure(); // the captions change height between beats

      // the globe turns on its own, then swings round to face Canada as the story starts
      spin += dt * 0.14;
      const toCanada = smooth(0.02, 0.22, p);
      const target = -CANADA_LON * DEG;
      const delta = ((((target - spin) % (2 * Math.PI)) + 3 * Math.PI) % (2 * Math.PI)) - Math.PI;
      uniforms.uRot.value = spin + delta * toCanada;
      uniforms.uTilt.value = 0.36 + (60 * DEG - 0.36) * toCanada;
      atmoMat.uniforms.uOpacity.value = 0.12 * (1 - smooth(0.04, 0.2, p));
      atmo.visible = atmoMat.uniforms.uOpacity.value > 0.002;

      pointer.x += (pointer.tx - pointer.x) * (1 - Math.exp(-dt * 3));
      pointer.y += (pointer.ty - pointer.y) * (1 - Math.exp(-dt * 3));
      const { sx, sy } = path(p, camPos, camLook);
      const aspect = w / Math.max(h, 1), portrait = aspect < 0.95;
      const fit = Math.max(1, (portrait ? 0.86 : 0.78) / aspect); // narrow screens: step back so the shapes fit the width
      camPos.sub(camLook).multiplyScalar(fit).add(camLook);
      camPos.x += pointer.x * 0.14; camPos.y += pointer.y * 0.09;
      camera.position.copy(camPos);
      camera.lookAt(camLook);
      camera.updateProjectionMatrix();
      // shift the picture off-centre without changing the perspective: right of the text on wide screens, below it on tall ones
      camera.projectionMatrix.elements[8] = portrait ? 0 : -sx;
      camera.projectionMatrix.elements[9] = portrait ? -sy : 0;
      camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
      renderer.render(scene, camera);
    };

    const start = () => { if (!raf && visible && !document.hidden) { last = 0; raf = requestAnimationFrame(frame); } };
    const stop = () => { if (raf) cancelAnimationFrame(raf); raf = 0; };
    const onVis = () => (document.hidden ? stop() : start());
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      pointer.tx = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.ty = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    const onLost = (e: Event) => { e.preventDefault(); stop(); failRef.current(); };

    const ro = new ResizeObserver(resize);
    ro.observe(el);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) start(); else stop(); });
    io.observe(el);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("pointermove", onMove, { passive: true });
    canvas.addEventListener("webglcontextlost", onLost);
    resize();
    start();

    return () => {
      stop(); ro.disconnect(); io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("webglcontextlost", onLost);
      geom.dispose(); mat.dispose(); atmoGeom.dispose(); atmoMat.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    };
  }, [progress, avoid]);

  return <div ref={box} className="story-in absolute inset-0" />;
}
