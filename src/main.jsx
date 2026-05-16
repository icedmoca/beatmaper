import React, { Component, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as THREE from "three";
import { Canvas, useFrame, useThree, extend } from "@react-three/fiber";
import { Reflector } from "three/examples/jsm/objects/Reflector.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import "./style.css";
extend({ Reflector, RoundedBoxGeometry });

/** FastAPI base URL (override with Vite env `VITE_API_BASE` if needed). */
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8008";
class ErrorBoundary extends Component {
  constructor(p) {
    super(p);
    this.state = { err: null };
  }
  static getDerivedStateFromError(err) {
    return { err };
  }
  componentDidCatch(err, info) {
    console.error("Beatmaper UI crash", err, info);
    window.__beatmaperLastError = {
      message: String(err?.message || err),
      stack: String(err?.stack || ""),
      info,
    };
  }
  render() {
    if (this.state.err)
      return (
        <div className="app">
          <section className="panel">
            <h1>Beatmaper preview recovered</h1>
            <p className="err">
              The visual preview hit a runtime error, but the page stayed alive.
            </p>
            <pre className="debugText">
              {String(this.state.err?.message || this.state.err)}
            </pre>
            <button onClick={() => this.setState({ err: null })}>
              Try reopening preview
            </button>
          </section>
        </div>
      );
    return this.props.children;
  }
}

function BeatViz({ beats = [] }) {
  const bars = useMemo(
    () =>
      Array.from({ length: 96 }, (_, i) => {
        let hit = beats[i] ?? 0;
        return {
          h: 24 + (Math.sin(i * 0.73) + 1) * 28 + (hit % 1) * 55,
          delay: (i % 16) * 0.035,
        };
      }),
    [beats],
  );
  return (
    <div className="viz">
      <div className="road">
        {bars.map((b, i) => (
          <i key={i} style={{ height: b.h, animationDelay: b.delay + "s" }} />
        ))}
      </div>
      <div className="saber red"></div>
      <div className="saber blue"></div>
    </div>
  );
}

const HIT_Z = -3.2;
const HAND_Z = -5.05;
const LOCAL_TIP = new THREE.Vector3(0, 2.2, 0);
const LOCAL_MID = new THREE.Vector3(0, 1.15, 0);
const LOCAL_ROOT = new THREE.Vector3(0, 0.08, 0);
function normalize2(v) {
  const l = Math.hypot(v[0] || 0, v[1] || 0, v[2] || 0) || 1;
  return [v[0] / l, v[1] / l, (v[2] || 0) / l];
}
function dot3(a, b) {
  return (
    (a[0] || 0) * (b[0] || 0) +
    (a[1] || 0) * (b[1] || 0) +
    (a[2] || 0) * (b[2] || 0)
  );
}
function segmentAabbHit(a, b, c, h) {
  let tmin = 0,
    tmax = 1;
  const d = new THREE.Vector3().subVectors(b, a);
  for (const ax of ["x", "y", "z"]) {
    if (Math.abs(d[ax]) < 1e-6) {
      if (a[ax] < c[ax] - h[ax] || a[ax] > c[ax] + h[ax]) return null;
    } else {
      const ood = 1 / d[ax];
      let t1 = (c[ax] - h[ax] - a[ax]) * ood;
      let t2 = (c[ax] + h[ax] - a[ax]) * ood;
      if (t1 > t2) {
        const tmp = t1;
        t1 = t2;
        t2 = tmp;
      }
      tmin = Math.max(tmin, t1);
      tmax = Math.min(tmax, t2);
      if (tmin > tmax) return null;
    }
  }
  return a.clone().add(d.multiplyScalar(tmin));
}
function cutVector(cut) {
  const map = {
    0: [0, 1, 0],
    1: [0, -1, 0],
    2: [-1, 0, 0],
    3: [1, 0, 0],
    4: [-1, 1, 0],
    5: [1, 1, 0],
    6: [-1, -1, 0],
    7: [1, -1, 0],
    8: [0, 0, 1],
  };
  return map[cut] || [0, -1, 0];
}
function cutAngle(cut, side) {
  const v = cutVector(cut);
  if (cut === 8) return side * 0.08;
  return Math.atan2(v[1], v[0]) * 0.55 + side * 0.1;
}
function impactFace(x, y, z) {
  const ax = Math.abs(x),
    ay = Math.abs(y),
    az = Math.abs(z);
  if (ax > ay && ax > az) return x > 0 ? "right" : "left";
  if (ay > ax && ay > az) return y > 0 ? "top" : "bottom";
  return z > 0 ? "back" : "front";
}
function sweptBladeHit(history, center, half, cut = 1) {
  if (!history || history.length < 2) return null;
  let best = null;
  for (let i = Math.max(1, history.length - 8); i < history.length; i++) {
    const a = history[i - 1],
      b = history[i];
    for (const part of ["mid", "tip"]) {
      const pa = a[part],
        pb = b[part];
      const hit = segmentAabbHit(pa, pb, center, half);
      if (hit) {
        const vel = pb.clone().sub(pa).multiplyScalar(60);
        const weight = part === "tip" ? 1 : 0.72;
        const score = vel.length() * weight;
        if (!best || score > best.score)
          best = {
            hit,
            part,
            vel,
            score,
            weight,
            angle: b.angle,
            bladeAxis: b.axis,
            history: history.slice(Math.max(0, i - 5), i + 1),
          };
      }
    }
  }
  if (cut === 8 && best && best.part !== "tip") return null;
  return best;
}
function validCut(cut, sweep) {
  const vel = sweep.vel || new THREE.Vector3();
  const speed = vel.length();
  if (speed < 0.35)
    return {
      valid: false,
      type: "too slow",
      directional: 0,
      stabAlign: 0,
      vector: [0, 0, 0],
      part: sweep.part,
    };
  const v = normalize2([vel.x, vel.y, vel.z]);
  const axis = normalize2([
    sweep.bladeAxis.x,
    sweep.bladeAxis.y,
    sweep.bladeAxis.z,
  ]);
  if (cut === 8) {
    const stab = Math.abs(dot3(v, axis));
    return {
      valid: sweep.part === "tip" && (stab > 0.28 || speed > 2.0),
      type: stab > 0.5 ? "tip stab" : "tip poke",
      directional: 1,
      stabAlign: Math.round(stab * 100) / 100,
      vector: v,
      part: sweep.part,
    };
  }
  const req = normalize2(cutVector(cut));
  const directional = dot3(v, req);
  return {
    valid: sweep.weight > 0.7 && (directional > 0.05 || speed > 2.6),
    type: speed > 4.2 ? "tip slash" : "controlled cut",
    directional: Math.round(directional * 100) / 100,
    stabAlign: Math.round(Math.abs(dot3(v, axis)) * 100) / 100,
    vector: v,
    part: sweep.part,
  };
}
function analyzeSwingHistory(history) {
  if (!history || history.length < 4)
    return { energy: 0, confidence: 0, intent: [0, 0, 0] };
  const h = history.slice(-8);
  const v = [];
  for (let i = 1; i < h.length; i++)
    v.push(
      h[i].tip
        .clone()
        .sub(h[i - 1].tip)
        .multiplyScalar(60),
    );
  const avg = v
    .reduce((a, x) => a.add(x), new THREE.Vector3())
    .divideScalar(Math.max(1, v.length));
  const speed = avg.length();
  return {
    energy: Math.min(1, speed / 6),
    confidence: Math.min(1, speed / 4.5),
    intent: normalize2([avg.x, avg.y, avg.z]),
  };
}

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}
function swingPlanForNote(note, side, hitZ) {
  const cut = note._cutDirection ?? 1;
  const v = cut === 8 ? [0, 0, 1] : cutVector(cut);
  const base = new THREE.Vector3(
    ((note._lineIndex ?? 1.5) - 1.5) * 1.05,
    -0.42 + (note._lineLayer ?? 0) * 0.62,
    hitZ - 0.18,
  );
  const prep = cut === 8 ? 0.18 : 0.58;
  const follow = cut === 8 ? 0.28 : 0.48;
  const start = base
    .clone()
    .add(
      new THREE.Vector3(
        -(v[0] || 0) * prep,
        -(v[1] || 0) * prep,
        cut === 8 ? -prep * 0.8 : 0,
      ),
    );
  const hit = base.clone();
  const end = base
    .clone()
    .add(
      new THREE.Vector3(
        (v[0] || 0) * follow,
        (v[1] || 0) * follow,
        cut === 8 ? follow * 0.95 : 0,
      ),
    );
  let angle =
    cut === 8 ? side * 0.1 : Math.atan2(v[1], v[0]) * 0.45 + side * 0.18;
  return { cut, v, start, hit, end, angle };
}

function clampHumanSaberPose(targetPos, desiredAngle, side) {
  // Player holds handles near body center. Saber blade should not flip upside down.
  // We clamp wrist travel and rotation, then let the tip/swing imply cut direction.
  const shoulder = new THREE.Vector3(side * 0.32, -1.02, -4.95);
  const maxReach = 2.15;
  const to = targetPos.clone().sub(shoulder);
  if (to.length() > maxReach)
    targetPos = shoulder.clone().add(to.normalize().multiplyScalar(maxReach));
  const minZ = -5.35,
    maxZ = -3.55;
  targetPos.z = Math.max(minZ, Math.min(maxZ, targetPos.z));
  targetPos.y = Math.max(-1.38, Math.min(0.55, targetPos.y));
  targetPos.x = Math.max(-1.85, Math.min(1.85, targetPos.x));
  // Keep blade generally upright/outward. No full inversion.
  let angle = desiredAngle;
  const min = -Math.PI * 0.78,
    max = Math.PI * 0.78;
  while (angle > Math.PI) angle -= Math.PI * 2;
  while (angle < -Math.PI) angle += Math.PI * 2;
  angle = Math.max(min, Math.min(max, angle));
  return { pos: targetPos, angle };
}
function NoteArrow({ cut = 1, color = 0 }) {
  const edge = color === 1 ? "#baf2ff" : "#ffb3c2";
  const rot =
    {
      0: 0,
      1: Math.PI,
      2: Math.PI / 2,
      3: -Math.PI / 2,
      4: Math.PI / 4,
      5: -Math.PI / 4,
      6: (Math.PI * 3) / 4,
      7: (-Math.PI * 3) / 4,
    }[Number(cut)] ?? 0;
  return (
    <group position={[0, 0, 0]} rotation={[0, 0, rot]}>
      {/* Soft outer glow halo (additive, no depth write) */}
      <mesh scale={[1.3, 1.18, 1.0]}>
        <coneGeometry args={[0.16, 0.4, 3]} />
        <meshBasicMaterial
          color="#ffffff"
          transparent
          opacity={0.28}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      {/* Mid glow */}
      <mesh scale={[1.12, 1.08, 1.0]}>
        <coneGeometry args={[0.16, 0.4, 3]} />
        <meshBasicMaterial
          color="#ffffff"
          transparent
          opacity={0.45}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      {/* Solid white core arrow */}
      <mesh>
        <coneGeometry args={[0.16, 0.4, 3]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>
    </group>
  );
}
function DotTarget({ color = 0 }) {
  const edge = color === 1 ? "#baf2ff" : "#ffb3c2";
  return (
    <group position={[0, 0, 0.34]}>
      <mesh>
        <torusGeometry args={[0.18, 0.025, 10, 36]} />
        <meshBasicMaterial color={edge} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.055, 14, 14]} />
        <meshBasicMaterial color={edge} />
      </mesh>
    </group>
  );
}
function SliceFragments({ info }) {
  const group = useRef();
  useFrame(() => {
    if (!group.current || !info) return;
    const age = (performance.now() - info.when) / 1000;
    group.current.visible = age < 0.8;
    group.current.children.forEach((m, i) => {
      const d = i === 0 ? -1 : 1;
      m.position.x = info.center.x + d * age * 0.42 * (info.vector?.[1] || 0.4);
      m.position.y = info.center.y - d * age * 0.42 * (info.vector?.[0] || 0.4);
      m.position.z = info.center.z - age * 0.18;
      if (m.material) m.material.opacity = Math.max(0, 0.7 - age * 0.9);
    });
  });
  if (!info) return null;
  const col = info.color === 1 ? "#2bbcff" : "#ff315a";
  return (
    <group ref={group}>
      <mesh
        position={[info.center.x, info.center.y, info.center.z]}
        rotation={[0, 0, info.angle]}
      >
        <boxGeometry args={[0.68, 0.32, 0.12]} />
        <meshBasicMaterial color={col} transparent opacity={0.68} />
      </mesh>
      <mesh
        position={[info.center.x, info.center.y, info.center.z]}
        rotation={[0, 0, info.angle]}
      >
        <boxGeometry args={[0.68, 0.32, 0.12]} />
        <meshBasicMaterial color={col} transparent opacity={0.68} />
      </mesh>
      <mesh
        position={[info.center.x, info.center.y, info.center.z + 0.08]}
        rotation={[0, 0, info.angle]}
      >
        <boxGeometry args={[0.78, 0.026, 0.035]} />
        <meshBasicMaterial color="#fff" transparent opacity={0.9} />
      </mesh>
    </group>
  );
}
function Saber({
  color = "red",
  side = -1,
  playing,
  clockRef,
  notes = [],
  bpm = 120,
  hitEvents,
}) {
  const group = useRef(),
    blade = useRef(),
    core = useRef(),
    glow = useRef(),
    bladeLight = useRef(),
    axisGroup = useRef();
  const history = useRef([]);
  const targetQ = useMemo(() => new THREE.Quaternion(), []);
  const smoothPower = useRef(0.25);
  const rootW = useMemo(() => new THREE.Vector3(), []),
    midW = useMemo(() => new THREE.Vector3(), []),
    tipW = useMemo(() => new THREE.Vector3(), []),
    handW = useMemo(() => new THREE.Vector3(), []);
  const q = useMemo(() => new THREE.Quaternion(), []);
  const colorType = color === "blue" ? 1 : 0;
  const saberColor = colorType ? "#2bbcff" : "#ff315a";
  const own = useMemo(
    () =>
      notes
        .filter((n) => Number(n.c) === colorType && Number(n.b) >= 0)
        .sort((a, b) => Number(a.b) - Number(b.b)),
    [notes, colorType],
  );
  const laneX = (x) => ((Number(x) || 0) - 1.5) * 0.72;
  const laneY = (y) => 0.72 + (Number(y) || 0) * 0.5;
  function world(local, out) {
    out.copy(local).applyQuaternion(q).add(handW);
    return out;
  }
  function nextNote(t) {
    let best = null,
      score = 999;
    for (const n of own) {
      const sec = (Number(n.b) * 60) / (bpm || 120),
        d = sec - t;
      if (d > -0.22 && d < 0.95 && Math.abs(d) < score) {
        best = { n, sec, d };
        score = Math.abs(d);
      }
    }
    return best;
  }
  useFrame((_, dt) => {
    const t = Number(clockRef.current) || (performance.now() / 1000) * 0.35;
    const pick = nextNote(t);
    let power = 0.25;
    let intent = [0, 1, 0];
    const shoulder = new THREE.Vector3(side * 0.46, 0.25, -4.85);
    let tipTarget = new THREE.Vector3(
      side * 0.5 + side * 0.04 * Math.sin(t * 1.1),
      2.15 + 0.07 * Math.sin(t * 0.9 + side),
      -4.4 + 0.04 * Math.sin(t * 1.3),
    );
    if (pick) {
      const n = pick.n,
        sec = pick.sec,
        cut = Number(n.d ?? 1),
        cv = cutVector(cut);
      intent = cv;
      const center = new THREE.Vector3(laneX(n.x), laneY(n.y), HIT_Z);
      const lead = Math.max(0.28, Math.min(0.6, (60 / (bpm || 120)) * 0.95));
      const follow = 0.28;
      const u = THREE.MathUtils.clamp(
        (t - (sec - lead)) / (lead + follow),
        0,
        1,
      );
      const e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      const dot = cut === 8 || cut === -1;
      if (dot) {
        const dir = center.clone().sub(shoulder).normalize();
        const thrust = Math.sin(e * Math.PI);
        const reach = 1.7 + 1.3 * thrust;
        tipTarget = shoulder.clone().addScaledVector(dir, reach);
        power = 0.5 + thrust * 1.1;
      } else {
        const impactDir = center.clone().sub(shoulder).normalize();
        const cvVec = new THREE.Vector3(cv[0], cv[1], 0);
        if (cvVec.lengthSq() < 1e-4) cvVec.set(0, -1, 0);
        cvVec.normalize();
        let swingAxis = new THREE.Vector3().crossVectors(impactDir, cvVec);
        if (swingAxis.lengthSq() < 1e-4) swingAxis.set(1, 0, 0);
        swingAxis.normalize();
        const swingArc = 0.95;
        const theta = (e - 0.5) * swingArc;
        const bladeDirRot = impactDir
          .clone()
          .applyAxisAngle(swingAxis, theta);
        tipTarget = shoulder
          .clone()
          .addScaledVector(bladeDirRot, LOCAL_TIP.y);
        power = 0.45 + Math.sin(e * Math.PI) * 1.2;
      }
    }
    const reachLen = LOCAL_TIP.y;
    const offset = tipTarget.clone().sub(shoulder);
    if (offset.lengthSq() < 0.01) offset.set(side * 0.2, 1, 0.4);
    const bladeDirTarget = offset.clone().normalize();
    if (offset.length() > reachLen) offset.setLength(reachLen);

    // Build the desired pose, then slerp/lerp the actual pose toward it.
    // This guarantees the sword never teleports between notes or between
    // idle and a swing — orientation flows continuously each frame.
    targetQ.setFromUnitVectors(new THREE.Vector3(0, 1, 0), bladeDirTarget);
    const dtClamped = Math.min(Math.max(dt, 1e-3), 0.05);
    const k = 1.0 - Math.exp(-22.0 * dtClamped);
    q.slerp(targetQ, k);
    smoothPower.current += (power - smoothPower.current) * k;
    // Recover the actual (smoothed) blade direction from the quaternion so
    // downstream world() math and history follow what's visually rendered.
    const bladeDir = new THREE.Vector3(0, 1, 0).applyQuaternion(q);

    handW.copy(shoulder);
    if (group.current) {
      group.current.position.copy(handW);
      group.current.quaternion.copy(q);
    }
    world(LOCAL_ROOT, rootW);
    world(LOCAL_MID, midW);
    world(LOCAL_TIP, tipW);
    history.current.push({
      t,
      root: rootW.clone(),
      mid: midW.clone(),
      tip: tipW.clone(),
      axis: bladeDir.clone(),
      angle: Math.atan2(bladeDir.y, bladeDir.x),
      intent,
    });
    while (history.current.length > 14) history.current.shift();
    if (hitEvents?.current) {
      hitEvents.current.sabers = hitEvents.current.sabers || {};
      hitEvents.current.sabers[colorType] = {
        color: colorType,
        hand: handW.clone(),
        root: rootW.clone(),
        mid: midW.clone(),
        tip: tipW.clone(),
        history: [...history.current],
        intent,
      };
    }
    const pwr = smoothPower.current;
    if (core.current) core.current.emissiveIntensity = 3.7 + pwr * 1.3;
    if (glow.current) glow.current.opacity = 0.22 + pwr * 0.14;
    if (blade.current?.scale) blade.current.scale.set(1, 1 + pwr * 0.025, 1);
    if (bladeLight.current) bladeLight.current.intensity = 2.4 + pwr * 4.2;
    if (axisGroup.current)
      axisGroup.current.visible = !!hitEvents?.current?.debugPreview;
  });
  return (
    <group ref={group}>
      <mesh
        position={[0, LOCAL_ROOT.y - 0.22, LOCAL_ROOT.z]}
        rotation={[Math.PI / 2, 0, 0]}
      >
        <cylinderGeometry args={[0.105, 0.13, 0.44, 24]} />
        <meshStandardMaterial
          color="#05070b"
          metalness={0.8}
          roughness={0.2}
          emissive={saberColor}
          emissiveIntensity={0.35}
        />
      </mesh>
      <mesh ref={blade} position={[0, 1.55, 0]}>
        <cylinderGeometry args={[0.038, 0.055, 2.95, 28]} />
        <meshStandardMaterial
          ref={core}
          color={saberColor}
          emissive={saberColor}
          emissiveIntensity={4.2}
          transparent
          opacity={0.94}
        />
      </mesh>
      <mesh position={[0, 1.55, 0]}>
        <cylinderGeometry args={[0.13, 0.18, 3.02, 28]} />
        <meshBasicMaterial
          ref={glow}
          color={saberColor}
          transparent
          opacity={0.34}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <pointLight
        ref={bladeLight}
        position={[0, 1.55, 0]}
        color={saberColor}
        intensity={2.4}
        distance={9}
        decay={1.8}
      />
      <group ref={axisGroup} visible={false}>
        <mesh position={[0, LOCAL_ROOT.y, LOCAL_ROOT.z]}>
          <sphereGeometry args={[0.08, 12, 12]} />
          <meshBasicMaterial color="#fff" />
        </mesh>
        <mesh position={[0, LOCAL_MID.y, LOCAL_MID.z]}>
          <sphereGeometry args={[0.07, 12, 12]} />
          <meshBasicMaterial color="#ffd34d" />
        </mesh>
        <mesh position={[0, LOCAL_TIP.y, LOCAL_TIP.z]}>
          <sphereGeometry args={[0.09, 12, 12]} />
          <meshBasicMaterial color="#00ff99" />
        </mesh>
      </group>
    </group>
  );
}
function MovingNote({ note, bpm, clockRef, loopSeconds, hitEvents }) {
  const group = useRef();
  const [cut, setCut] = useState(null);
  const done = useRef(false);
  const base = useMemo(
    () => ({
      beat: Number(note.b || 0),
      x: Number(note.x ?? 1),
      y: Number(note.y ?? 1),
      color: Number(note.c ?? 0),
      cut: Number(note.d ?? 1),
    }),
    [note],
  );
  const laneX = (base.x - 1.5) * 0.72,
    laneY = 0.72 + base.y * 0.5,
    half = { x: 0.36, y: 0.36, z: 0.25 };
  const sec = useMemo(() => (base.beat * 60) / (bpm || 120), [base.beat, bpm]);
  useFrame(() => {
    if (done.current) {
      if (group.current && group.current.visible) group.current.visible = false;
      return;
    }
    const t = Number(clockRef.current) || 0;
    const age = sec - t;
    if (age > 2.5 || age < -0.3) {
      if (group.current && group.current.visible) group.current.visible = false;
      return;
    }
    const z = HIT_Z + (age / 2.1) * 10.5;
    if (group.current) {
      group.current.position.set(laneX, laneY, z);
      // Grow as the note approaches the sabers — small at spawn, full size
      // by the time it reaches the impact plane, then stays full size as
      // it passes by.
      const tApproach = Math.max(0, Math.min(1, (2.5 - age) / 2.5));
      const eased = tApproach * tApproach * (3 - 2 * tApproach);
      const s = 0.32 + 0.68 * eased;
      group.current.scale.set(s, s, s);
      group.current.visible = true;
    }
    if (Math.abs(z - HIT_Z) > 0.48) return;
    const saber = hitEvents?.current?.sabers?.[base.color];
    if (!saber?.history?.length) return;
    const sweep = sweptBladeHit(
      saber.history,
      { x: laneX, y: laneY, z },
      half,
      base.cut,
    );
    if (sweep && validCut(base.cut, sweep)) {
      done.current = true;
      const v = cutVector(base.cut);
      setCut({
        when: performance.now(),
        center: { x: laneX, y: laneY, z: HIT_Z },
        angle: Math.atan2(v[1], v[0]) + Math.PI / 2,
        vector: v,
        color: base.color,
      });
    }
  });
  const col = base.color === 1 ? "#2bbcff" : "#ff315a";
  return (
    <>
      {!done.current && (
        <group ref={group}>
          <mesh>
            <roundedBoxGeometry args={[0.68, 0.68, 0.5, 5, 0.12]} />
            <meshStandardMaterial
              color={base.color === 1 ? "#123e61" : "#611225"}
              emissive={col}
              emissiveIntensity={1.1}
              transparent
              opacity={0.72}
            />
          </mesh>
          {base.cut === 8 ? (
            <DotTarget color={base.color} />
          ) : (
            <NoteArrow cut={base.cut} color={base.color} />
          )}
        </group>
      )}
      {cut && <SliceFragments info={cut} />}
    </>
  );
}
function CameraController({ flyMode, setFlyMode }) {
  const { camera, gl } = useThree();
  const keys = useRef({});
  const yaw = useRef(Math.PI);
  const pitch = useRef(-0.08);
  const initialized = useRef(false);
  useEffect(() => {
    if (!initialized.current) {
      camera.position.set(0, 1.62, -7.4);
      camera.lookAt(0, 1.12, -0.6);
      camera.updateProjectionMatrix();
      initialized.current = true;
    }
  }, [camera]);
  useEffect(() => {
    if (!flyMode) return;
    const canvas = gl.domElement;
    const dir = new THREE.Vector3();
    camera.getWorldDirection(dir);
    yaw.current = Math.atan2(dir.x, dir.z);
    pitch.current = Math.asin(THREE.MathUtils.clamp(dir.y, -1, 1));
    const flyCodes = new Set([
      "KeyW",
      "KeyA",
      "KeyS",
      "KeyD",
      "Space",
      "ShiftLeft",
      "ShiftRight",
      "ControlLeft",
      "ControlRight",
    ]);
    const onKeyDown = (e) => {
      keys.current[e.code] = true;
      if (flyCodes.has(e.code)) e.preventDefault();
      if (e.code === "Escape") {
        if (document.pointerLockElement) document.exitPointerLock?.();
      }
    };
    const onKeyUp = (e) => {
      keys.current[e.code] = false;
    };
    const onCanvasClick = () => {
      if (document.pointerLockElement !== canvas) canvas.requestPointerLock?.();
    };
    const onMouseMove = (e) => {
      if (document.pointerLockElement !== canvas) return;
      yaw.current -= e.movementX * 0.0025;
      pitch.current -= e.movementY * 0.0025;
      const lim = Math.PI / 2 - 0.05;
      pitch.current = Math.max(-lim, Math.min(lim, pitch.current));
    };
    canvas.addEventListener("click", onCanvasClick);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("mousemove", onMouseMove);
    canvas.requestPointerLock?.();
    return () => {
      canvas.removeEventListener("click", onCanvasClick);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("mousemove", onMouseMove);
      if (document.pointerLockElement === canvas) document.exitPointerLock?.();
      keys.current = {};
    };
  }, [flyMode, gl, camera]);
  useFrame((_, dt) => {
    if (!flyMode) {
      camera.position.lerp(new THREE.Vector3(0, 1.62, -7.4), 0.12);
      camera.lookAt(0, 1.12, -0.6);
      return;
    }
    const e = new THREE.Euler(pitch.current, yaw.current, 0, "YXZ");
    camera.quaternion.setFromEuler(e);
    const k = keys.current;
    const fast = k.ControlLeft || k.ControlRight ? 14 : 5;
    const step = fast * Math.min(dt, 0.05);
    const fwd = new THREE.Vector3();
    camera.getWorldDirection(fwd);
    const right = new THREE.Vector3()
      .crossVectors(fwd, new THREE.Vector3(0, 1, 0))
      .normalize();
    if (k.KeyW) camera.position.addScaledVector(fwd, step);
    if (k.KeyS) camera.position.addScaledVector(fwd, -step);
    if (k.KeyD) camera.position.addScaledVector(right, step);
    if (k.KeyA) camera.position.addScaledVector(right, -step);
    if (k.Space) camera.position.y += step;
    if (k.ShiftLeft || k.ShiftRight) camera.position.y -= step;
  });
  return null;
}
const MAX_FLOOR_EMITTERS = 16;
const MAX_FLOOR_BLADES = 4;
const MATTE_FLOOR_SHADER = {
  name: "MatteReflectorShader",
  uniforms: {
    color: { value: null },
    tDiffuse: { value: null },
    textureMatrix: { value: null },
    uTime: { value: 0 },
    uFresnelPower: { value: 2.4 },
    uReflectStrength: { value: 1.5 },
    uBaseColor: { value: new THREE.Color("#03040a") },
    uEmitterPos: {
      value: Array.from(
        { length: MAX_FLOOR_EMITTERS },
        () => new THREE.Vector3(),
      ),
    },
    uEmitterCol: {
      value: Array.from(
        { length: MAX_FLOOR_EMITTERS },
        () => new THREE.Color(0, 0, 0),
      ),
    },
    uEmitterInt: { value: new Float32Array(MAX_FLOOR_EMITTERS) },
    uEmitterCount: { value: 0 },
    uBladeA: {
      value: Array.from(
        { length: MAX_FLOOR_BLADES },
        () => new THREE.Vector3(),
      ),
    },
    uBladeB: {
      value: Array.from(
        { length: MAX_FLOOR_BLADES },
        () => new THREE.Vector3(),
      ),
    },
    uBladeCol: {
      value: Array.from(
        { length: MAX_FLOOR_BLADES },
        () => new THREE.Color(0, 0, 0),
      ),
    },
    uBladeInt: { value: new Float32Array(MAX_FLOOR_BLADES) },
    uBladeCount: { value: 0 },
  },
  vertexShader: `
    uniform mat4 textureMatrix;
    varying vec4 vUv;
    varying vec3 vWorldPos;
    varying vec3 vWorldNormal;
    void main() {
      vUv = textureMatrix * vec4(position, 1.0);
      vec4 wp = modelMatrix * vec4(position, 1.0);
      vWorldPos = wp.xyz;
      vWorldNormal = normalize(mat3(modelMatrix) * normal);
      gl_Position = projectionMatrix * viewMatrix * wp;
    }
  `,
  fragmentShader: `
    #define MAX_FLOOR_EMITTERS 16
    #define MAX_FLOOR_BLADES 4
    uniform vec3 color;
    uniform sampler2D tDiffuse;
    uniform float uTime;
    uniform float uFresnelPower;
    uniform float uReflectStrength;
    uniform vec3 uBaseColor;
    uniform vec3 uEmitterPos[MAX_FLOOR_EMITTERS];
    uniform vec3 uEmitterCol[MAX_FLOOR_EMITTERS];
    uniform float uEmitterInt[MAX_FLOOR_EMITTERS];
    uniform int uEmitterCount;
    uniform vec3 uBladeA[MAX_FLOOR_BLADES];
    uniform vec3 uBladeB[MAX_FLOOR_BLADES];
    uniform vec3 uBladeCol[MAX_FLOOR_BLADES];
    uniform float uBladeInt[MAX_FLOOR_BLADES];
    uniform int uBladeCount;
    varying vec4 vUv;
    varying vec3 vWorldPos;
    varying vec3 vWorldNormal;

    float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    float vnoise(vec2 p){
      vec2 i = floor(p);
      vec2 f = fract(p);
      vec2 u = f*f*(3.0-2.0*f);
      return mix(
        mix(hash(i+vec2(0.,0.)), hash(i+vec2(1.,0.)), u.x),
        mix(hash(i+vec2(0.,1.)), hash(i+vec2(1.,1.)), u.x),
        u.y);
    }

    void main(){
      vec2 ndc = vUv.xy / vUv.w;
      float n1 = vnoise(ndc * 1.8 + vec2(uTime * 0.04, uTime * 0.025));

      // === Pass 1: SINGLE geometry reflection sample.
      // No offsets, no kernel, no duplicated objects. Heavily attenuated and
      // tonemapped so it reads as a faint, subtle ghost of the scene rather
      // than a clear mirror image.
      vec3 reflRaw = texture2DProj(tDiffuse, vUv).rgb;
      vec3 refl = reflRaw / (1.0 + reflRaw * 0.9);

      // === Pass 2: wide color wash (light only).
      // 24 samples on a wider disc, but each sample is reduced to its
      // red-or-blue saber/cube SATURATION before being added. Yellow lane
      // lines (high R+G, low B) score zero and contribute nothing.
      // Dividing by total tap count (not just bright taps) means a single
      // bright hit cannot reproduce the silhouette — it just lifts the haze.
      // === Pass 2: analytic world-space glow emitters with CHROMA-PRESERVING
      // accumulation. Color direction and energy are accumulated separately:
      //   colorAcc = Σ (emitterColor * intensity * falloff)   -> chromaticity
      //   energyAcc = Σ (intensity * falloff)                 -> total energy
      // After the loop we normalize colorAcc by its max channel so RGB cannot
      // all peg to 1.0 simultaneously, and apply a Reinhard rolloff to energy.
      // Red + blue overlap stays saturated (magenta/violet), never white.
      vec3 colorAcc = vec3(0.0);
      float energyAcc = 0.0;
      for (int e = 0; e < MAX_FLOOR_EMITTERS; e++) {
        if (e >= uEmitterCount) break;
        vec3 ep = uEmitterPos[e];
        vec2 d2 = vWorldPos.xz - ep.xz;
        float h = max(0.0, ep.y - vWorldPos.y);
        // Slight stretch along the lane (world-z) for cinematic streak
        float stretch = d2.y * d2.y * 0.45;
        float r2 = max(dot(d2, d2) - stretch + h * h * 0.22, 0.0);
        // Two-lobe field: tight bright core + wide soft tail.
        // The wide tail is what lets adjacent red/blue pools overlap at low
        // energy so the boundary between them becomes a smooth color gradient
        // instead of a hard chroma snap.
        float radius = 1.32;
        float core = exp(-r2 / (radius * radius) * 1.15);
        float tail = exp(-r2 / (radius * radius * 4.0));
        float falloff = core * 0.85 + tail * 0.20;
        float contribution = uEmitterInt[e] * falloff;
        colorAcc += uEmitterCol[e] * contribution;
        energyAcc += contribution;
      }

      // === Blade emitters: anisotropic capsule (line-segment) falloff.
      // Closest point on segment in floor plane -> tight perpendicular falloff
      // gives thin elongated streaks aligned with each saber's projected blade.
      for (int b = 0; b < MAX_FLOOR_BLADES; b++) {
        if (b >= uBladeCount) break;
        vec3 A = uBladeA[b];
        vec3 B = uBladeB[b];
        vec2 a = A.xz;
        vec2 bv = B.xz;
        vec2 ab = bv - a;
        vec2 fp = vWorldPos.xz;
        float abLen2 = max(dot(ab, ab), 1e-5);
        float tProj = clamp(dot(fp - a, ab) / abLen2, 0.0, 1.0);
        vec2 closest = a + ab * tProj;
        vec2 perp = fp - closest;
        float perpD2 = dot(perp, perp);

        // Height of the blade above the floor at the closest projected point
        float bladeH = mix(A.y, B.y, tProj);
        float h = max(0.0, bladeH - vWorldPos.y);

        // Anisotropic falloff:
        //   tight across the blade (perpRadius small -> thin streak)
        //   along the blade is "free" because distance is zero on segment,
        //   so the streak naturally stretches to the blade's projected length
        float perpRadius = 0.30;
        float perpFall = exp(-perpD2 / (perpRadius * perpRadius) * 1.6);
        float heightFall = exp(-h * h * 0.18);

        // Soft caps at the segment ends so streaks fade out gently
        float capSoft = 1.0
          - smoothstep(0.94, 1.10, tProj)
          - smoothstep(0.06, -0.10, tProj);
        capSoft = clamp(capSoft, 0.0, 1.0);

        float falloff = perpFall * heightFall * capSoft;
        float contribution = uBladeInt[b] * falloff;
        colorAcc += uBladeCol[b] * contribution;
        energyAcc += contribution;
      }

      // Energy-gated chroma normalization.
      // At high energy (near an emitter) we want the saturated chroma so
      // red + blue mix to magenta without white blowout. At low energy
      // (boundary tails between two pools) the raw additive accumulator IS
      // already a smooth color gradient — normalizing it would snap it to
      // whichever channel happens to be slightly dominant. So blend.
      float maxC = max(colorAcc.r, max(colorAcc.g, colorAcc.b));
      vec3 chromaNorm = colorAcc / max(maxC, 1e-5);
      // Raw additive direction, kept on a comparable scale by dividing by
      // its own length — this preserves the smooth red→purple→blue ramp.
      vec3 chromaSoft = colorAcc / max(length(colorAcc), 1e-5);
      float normT = smoothstep(0.35, 1.30, energyAcc);
      vec3 chroma = mix(chromaSoft, chromaNorm, normT);

      // Magenta bias only at high energy (where normalization is in effect).
      // At low energy we let the natural additive gradient through unsuppressed.
      float overlap = min(chroma.r, chroma.b);
      float gSupp = mix(1.0, 0.25, normT);     // 1.0 = no suppression
      chroma.g = mix(chroma.g, chroma.g * gSupp, overlap);

      // Reinhard-style luminance compression — stronger now (asymptotes ~1.8)
      float compressed = energyAcc / (1.0 + energyAcc * 0.55);
      // Crush mid/low energy with a gamma curve so faint spill goes to near-
      // black, while hotspots stay close to their previous brightness.
      compressed = pow(compressed, 1.85);

      vec3 glow = chroma * compressed;

      // Fresnel (stronger at grazing angles)
      vec3 V = normalize(cameraPosition - vWorldPos);
      float ndv = clamp(dot(normalize(vWorldNormal), V), 0.0, 1.0);
      float fres = pow(1.0 - ndv, uFresnelPower);

      // Gentle distance fade
      float dist = length(cameraPosition.xz - vWorldPos.xz);
      float distFade = clamp(exp(-dist * 0.035), 0.25, 1.0);

      // Subtle single-sample reflection on dark base — visible only at grazing
      vec3 tinted = refl * color * uReflectStrength;
      float reflMix = (0.06 + fres * 0.55) * distFade;
      vec3 outCol = mix(uBaseColor, tinted + uBaseColor * 0.45, min(reflMix, 0.9));

      // Analytic emitter glow — clean, no texture sampling artifacts possible
      outCol += glow * (0.22 + fres * 0.28) * distFade;

      // Brightness shimmer only (no color tint — can't introduce green)
      outCol *= 1.0 + (n1 - 0.5) * 0.04;

      gl_FragColor = vec4(outCol, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }
  `,
};

function ReflectiveFloor({ notes = [], bpm = 120, clockRef, hitEventsRef }) {
  const geom = useMemo(() => new THREE.PlaneGeometry(5.6, 24, 1, 1), []);
  const reflectorArgs = useMemo(
    () => [
      geom,
      {
        textureWidth: 768,
        textureHeight: 768,
        color: 0x2a2a36,
        clipBias: 0.003,
        shader: MATTE_FLOOR_SHADER,
      },
    ],
    [geom],
  );
  const reflectorRef = useRef();
  // Cleaner red/blue for floor emitters: low green so red+blue overlap mixes
  // into magenta/violet, not into white via the cyan-green saber tint.
  const redCol = useMemo(() => new THREE.Color("#ff1240"), []);
  const blueCol = useMemo(() => new THREE.Color("#2a30ff"), []);
  useFrame((_, dt) => {
    const r = reflectorRef.current;
    if (!r || !r.material) return;
    const u = r.material.uniforms;
    if (u.uTime) u.uTime.value += dt;

    // Build the live emitter list
    let idx = 0;
    const pushEmitter = (x, y, z, col, intensity) => {
      if (idx >= MAX_FLOOR_EMITTERS) return;
      u.uEmitterPos.value[idx].set(x, y, z);
      u.uEmitterCol.value[idx].copy(col);
      u.uEmitterInt.value[idx] = intensity;
      idx++;
    };

    // 1) Sabers as line-segment (blade) emitters — root→tip
    const sabers = hitEventsRef?.current?.sabers || {};
    const red = sabers[0];
    const blue = sabers[1];
    let bIdx = 0;
    const pushBlade = (A, B, col, intensity) => {
      if (bIdx >= MAX_FLOOR_BLADES) return;
      u.uBladeA.value[bIdx].copy(A);
      u.uBladeB.value[bIdx].copy(B);
      u.uBladeCol.value[bIdx].copy(col);
      u.uBladeInt.value[bIdx] = intensity;
      bIdx++;
    };
    if (red?.root && red?.tip) pushBlade(red.root, red.tip, redCol, 2.4);
    if (blue?.root && blue?.tip) pushBlade(blue.root, blue.tip, blueCol, 2.4);
    u.uBladeCount.value = bIdx;

    // 2) Closest active notes
    const t = Number(clockRef?.current) || 0;
    const bpmSafe = Number(bpm) || 120;
    // Find visible notes, pick the nearest by |age|
    const candidates = [];
    for (let i = 0; i < notes.length; i++) {
      const n = notes[i];
      const sec = (Number(n.b) * 60) / bpmSafe;
      const age = sec - t;
      if (age < -0.25 || age > 2.0) continue;
      candidates.push({ n, age });
    }
    candidates.sort((a, b) => Math.abs(a.age) - Math.abs(b.age));
    const slots = Math.max(0, MAX_FLOOR_EMITTERS - idx);
    for (let i = 0; i < Math.min(slots, candidates.length); i++) {
      const { n, age } = candidates[i];
      const x = (Number(n.x) - 1.5) * 0.72;
      const y = 0.72 + Number(n.y) * 0.5;
      const z = HIT_Z + (age / 2.1) * 10.5;
      const col = Number(n.c) === 1 ? blueCol : redCol;
      // Stronger near impact, weaker far away
      const proximity = Math.max(0, 1 - Math.abs(age) / 1.6);
      pushEmitter(x, y, z, col, 0.8 + proximity * 1.9);
    }

    u.uEmitterCount.value = idx;
  });
  return (
    <reflector
      ref={reflectorRef}
      args={reflectorArgs}
      position={[0, -0.96, 2.6]}
      rotation={[-Math.PI / 2, 0, 0]}
    />
  );
}
function LaneScaffold() {
  return (
    <group>
      {[-1.44, -1.08, -0.36, 0.36, 1.08, 1.44].map((x, i) => (
        <group
          key={i}
          position={[x, -0.945, 2.6]}
          rotation={[Math.PI / 2, 0, 0]}
        >
          {/* Soft neon halo (additive, no depth write) */}
          <mesh>
            <boxGeometry args={[0.055, 22, 0.055]} />
            <meshBasicMaterial
              color="#d7ff00"
              transparent
              opacity={0.16}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </mesh>
          {/* Bright thin core */}
          <mesh>
            <boxGeometry args={[0.018, 22, 0.018]} />
            <meshBasicMaterial
              color="#eaff5e"
              transparent
              opacity={0.65}
            />
          </mesh>
        </group>
      ))}
      <mesh position={[0, 1.18, HIT_Z]}>
        <boxGeometry args={[3.2, 1.9, 0.025]} />
        <meshBasicMaterial color="#d7ff00" transparent opacity={0.1} />
      </mesh>
      <pointLight position={[0, 3, -3]} intensity={0.6} color="#d7ff00" distance={9} decay={2.2} />
      <pointLight position={[-2, 2, -5]} intensity={1.8} color="#ff315a" distance={10} decay={1.8} />
      <pointLight position={[2, 2, -5]} intensity={1.8} color="#2bbcff" distance={10} decay={1.8} />
      <pointLight position={[0, 1.5, 4]} intensity={1.2} color="#8ad8ff" distance={14} decay={1.8} />
    </group>
  );
}
function GameplayScene({
  notes = [],
  bpm = 120,
  playing,
  flyMode,
  setFlyMode,
  clockRef,
  debugPreview,
}) {
  notes = Array.isArray(notes) ? notes : [];
  bpm = Number(bpm) || 120;
  const hitEvents = useRef({ sabers: {} });
  const localClockRef = useRef({ current: 0 });
  clockRef = clockRef || localClockRef;
  const usable = useMemo(
    () => notes.filter((n) => Number(n.b) >= 0).slice(0, 900),
    [notes],
  );
  const loopSeconds = useMemo(
    () =>
      Math.max(
        8,
        ...usable.map((n) => (Number(n.b || 0) * 60) / (bpm || 120) + 4),
      ),
    [usable, bpm],
  );
  hitEvents.current.loopSeconds = loopSeconds;
  hitEvents.current.hitZ = HIT_Z;
  hitEvents.current.debugPreview = debugPreview;
  return (
    <>
      <CameraController flyMode={flyMode} setFlyMode={setFlyMode} />
      <color attach="background" args={["#05060f"]} />
      <ambientLight intensity={0.65} />
      <fog attach="fog" args={["#05060f", 7, 18]} />
      <ReflectiveFloor
        notes={usable}
        bpm={bpm}
        clockRef={clockRef}
        hitEventsRef={hitEvents}
      />
      <LaneScaffold />
      <Saber
        color="red"
        side={-1}
        playing={playing}
        clockRef={clockRef}
        notes={usable}
        bpm={bpm}
        hitEvents={hitEvents}
      />
      <Saber
        color="blue"
        side={1}
        playing={playing}
        clockRef={clockRef}
        notes={usable}
        bpm={bpm}
        hitEvents={hitEvents}
      />
      {usable.map((n, i) => (
        <MovingNote
          key={i}
          note={n}
          bpm={bpm}
          clockRef={clockRef}
          loopSeconds={loopSeconds}
          hitEvents={hitEvents}
        />
      ))}
    </>
  );
}
function GameplayPreview({ res }) {
  res = res || {};
  res.preview = Array.isArray(res.preview) ? res.preview : [];
  res.bpm = Number(res.bpm) || 120;
  res.mode = res.mode || "Standard";
  const [playing, setPlaying] = useState(false);
  const [flyMode, setFlyMode] = useState(false);
  const [debugPreview, setDebugPreview] = useState(false);
  const audioRef = useRef(null);
  const clockRef = useRef(0);
  useEffect(() => {
    let raf;
    const tick = () => {
      const a = audioRef.current;
      clockRef.current = a && !isNaN(a.currentTime) ? a.currentTime : 0;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  const rawNotes = res?.previewNotes || [];
  const notes = useMemo(
    () =>
      rawNotes.map((n) => ({
        b: Number(n.b ?? n._time ?? 0),
        x: Number(n.x ?? n._lineIndex ?? 1),
        y: Number(n.y ?? n._lineLayer ?? 1),
        c: Number(n.c ?? n._type ?? 0),
        d: Number(n.d ?? n._cutDirection ?? 1),
      })),
    [rawNotes],
  );
  const audioUrl = res?.audioPreview
    ? API_BASE + res.audioPreview
    : null;
  useEffect(() => {
    setPlaying(false);
    setFlyMode(false);
    setTimeout(() => {
      if (audioRef.current) {
        audioRef.current.currentTime = 0;
      }
    }, 0);
  }, [res.download]);
  async function togglePlay() {
    const a = audioRef.current;
    if (!a) {
      setPlaying((p) => !p);
      return;
    }
    try {
      if (playing) {
        a.pause();
        setPlaying(false);
      } else {
        await a.play();
        setPlaying(true);
      }
    } catch (e) {
      setPlaying(true);
    }
  }
  async function restart() {
    const a = audioRef.current;
    if (a) {
      a.currentTime = 0;
      try {
        await a.play();
      } catch {}
      setPlaying(true);
    }
  }
  return (
    <section className="panel simPanel">
      <div className="simHead">
        <div>
          <h2>Generated gameplay simulation</h2>
          <p>
            Audio-synced Three.js preview. The note positions and saber slashes
            are driven by the song playback time.
          </p>
        </div>
        <div className="simButtons">
          <button className="simBtn" onClick={togglePlay}>
            {playing ? "Pause song" : "Play song"}
          </button>
          <button className="simBtn" onClick={restart}>
            Restart synced
          </button>
          <button
            className={"simBtn " + (flyMode ? "active" : "")}
            onClick={() => setFlyMode((v) => !v)}
          >
            {flyMode ? "Exit fly mode" : "Fly mode"}
          </button>
          <button
            className={"simBtn " + (debugPreview ? "active" : "")}
            onClick={() => setDebugPreview((v) => !v)}
          >
            Debug hitboxes
          </button>
        </div>
      </div>
      {audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          controls
          className="audioBar"
        />
      )}
      {flyMode && (
        <div className="flyHelp">
          <b>Fly mode active:</b> WASD move · mouse look · Space up · Shift down
          · Ctrl faster · Pause song to freeze notes · double-tap Space toggles
          · Esc releases mouse
        </div>
      )}
      <div className="gameCanvas">
        <Canvas
          key={res.download}
          camera={{ position: [0, 1.65, -7.6], fov: 78, near: 0.1, far: 120 }}
          gl={{
            antialias: true,
            powerPreference: "high-performance",
            alpha: false,
          }}
        >
          <GameplayScene
            notes={notes}
            bpm={res?.analysis?.bpm || res.bpm || 120}
            playing={playing}
            flyMode={flyMode}
            setFlyMode={setFlyMode}
            audioRef={audioRef}
            njs={res.njs || 12}
            jumpOffset={res.jumpOffset || 0}
            debugPreview={debugPreview}
            clockRef={clockRef}
          />
        </Canvas>
      </div>
      <p className="path">
        Previewing {notes.length} generated notes from the exported Expert
        Standard map. Use “Restart synced” if you want the song and map to start
        at beat zero together.
      </p>
    </section>
  );
}

const defaultSettings = {
  density: 0.34,
  streams: 0.08,
  njs: 10.5,
  offset: 0,
  difficulty: "Expert",
  seed: 9001,
  maxSimultaneous: 2,
  doubles: true,
  bombs: true,
  walls: true,
  lights: true,
  subdivisions: true,
  minDensity: true,
  directInstrument: false,
  multiDifficulty: true,
  stabDots: true,
  style: "flowy dance",
};
function ControlPanel({ settings, setSettings, preset, setPreset }) {
  const set = (k, v) => {
    setPreset("Custom");
    setSettings((o) => ({ ...o, [k]: v }));
  };
  const Toggle = ({ id, label, desc }) => (
    <label className="toggle">
      <input
        type="checkbox"
        checked={settings[id]}
        onChange={(e) => set(id, e.target.checked)}
      />
      <span>
        <b>{label}</b>
        <small>{desc}</small>
      </span>
    </label>
  );
  const Slider = ({ id, label, min, max, step, unit = "" }) => (
    <label className="slider">
      <span>
        <b>{label}</b>
        <em>
          {settings[id]}
          {unit}
        </em>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={settings[id]}
        onChange={(e) => set(id, Number(e.target.value))}
      />
    </label>
  );
  return (
    <section className="controls">
      <div className="controlsHead">
        <div>
          <h2>Generation controls</h2>
          <p>
            Normal by default, with optional Fun and Overkill presets. These
            settings change the actual Beat Saber map file that gets exported.
          </p>
        </div>
        <div className="presetBtns">
          <button
            className={
              "miniBtn preset " + (preset === "Normal" ? "selected" : "")
            }
            onClick={() => {
              setPreset("Normal");
              setSettings(defaultSettings);
            }}
          >
            Normal
          </button>
          <button
            className={"miniBtn preset " + (preset === "Fun" ? "selected" : "")}
            onClick={() => {
              setPreset("Fun");
              setSettings((o) => ({
                ...defaultSettings,
                density: 1.1,
                streams: 0.75,
                njs: 14,
                maxSimultaneous: 3,
              }));
            }}
          >
            Fun
          </button>
          <button
            className={
              "miniBtn preset hot " + (preset === "Overkill" ? "selected" : "")
            }
            onClick={() => {
              setPreset("Overkill");
              setSettings((o) => ({
                ...defaultSettings,
                density: 2.0,
                streams: 1.8,
                njs: 17,
                maxSimultaneous: 5,
                difficulty: "ExpertPlus",
              }));
            }}
          >
            Overkill
          </button>
        </div>
      </div>
      <div className="controlGrid">
        <Slider
          id="density"
          label="Overall density"
          min="0.4"
          max="3"
          step="0.05"
          unit="x"
        />
        <Slider
          id="streams"
          label="Stream aggression"
          min="0"
          max="2.5"
          step="0.05"
          unit="x"
        />
        <Slider id="njs" label="Note jump speed" min="8" max="24" step="0.5" />
        <Slider id="offset" label="Jump offset" min="-1" max="2" step="0.1" />
        <Slider
          id="maxSimultaneous"
          label="Max simultaneous blocks"
          min="1"
          max="6"
          step="1"
        />
        <label className="select">
          <span>
            <b>Difficulty label</b>
          </span>
          <select
            value={settings.difficulty}
            onChange={(e) => set("difficulty", e.target.value)}
          >
            <option>Hard</option>
            <option>Expert</option>
            <option>ExpertPlus</option>
          </select>
        </label>
        <label className="select">
          <span>
            <b>Style brain</b>
          </span>
          <select
            value={settings.style}
            onChange={(e) => set("style", e.target.value)}
          >
            <option>flowy dance</option>
            <option>ranked tech</option>
            <option>ost-like</option>
            <option>speed map</option>
            <option>accuracy map</option>
            <option>fitness map</option>
            <option>cinematic map</option>
          </select>
        </label>
        <label className="seed">
          <span>
            <b>Seed</b>
            <small>same seed = repeatable pattern</small>
          </span>
          <input
            type="number"
            value={settings.seed}
            onChange={(e) => set("seed", Number(e.target.value) || 0)}
          />
        </label>
      </div>
      <div className="toggles">
        <Toggle
          id="subdivisions"
          label="Beat subdivisions"
          desc="adds 1/8 and 1/4 timing detail"
        />
        <Toggle
          id="doubles"
          label="Big doubles"
          desc="strong beat two-hand hits"
        />
        <Toggle
          id="minDensity"
          label="Fill sparse gaps"
          desc="keeps maps from feeling empty"
        />
        <Toggle
          id="directInstrument"
          label="Direct instrument mode"
          desc="abstract conductor gestures for live musicians"
        />
        <Toggle
          id="multiDifficulty"
          label="Multi-difficulty export"
          desc="exports Easy through ExpertPlus variants"
        />
        <Toggle
          id="stabDots"
          label="Rare stab dots"
          desc="occasional circle blocks you poke straight through"
        />
        <Toggle
          id="bombs"
          label="Bomb accents"
          desc="optional dodge/avoid objects"
        />
        <Toggle id="walls" label="Wall accents" desc="safe sparse obstacles" />
        <Toggle
          id="lights"
          label="Light events"
          desc="basic environment pulses"
        />
      </div>
      <p className="controlHint">
        Direct Instrument Mode maps bass, vocal/mid, and high bands into
        abstract conductor-like gestures. Export remains standard Beat Saber v2
        format.
      </p>
    </section>
  );
}

function App() {
  const [busy, setBusy] = useState(false),
    [res, setRes] = useState(null),
    [err, setErr] = useState("");
  const [settings, setSettings] = useState(defaultSettings);
  const [preset, setPreset] = useState("Normal");
  async function upload(e) {
    let f = e.target.files[0];
    if (!f) return;
    setBusy(true);
    setErr("");
    setRes(null);
    let fd = new FormData();
    fd.append("file", f);
    Object.entries(settings).forEach(([k, v]) => fd.append(k, String(v)));
    try {
      let r = await fetch(API_BASE + "/analyze", {
        method: "POST",
        body: fd,
      });
      let text = await r.text();
      let j;
      try {
        j = JSON.parse(text);
      } catch {
        j = { detail: text };
      }
      if (!r.ok) throw Error(j.detail || "backend failed");
      setRes(j);
    } catch (x) {
      let m = x?.message || String(x);
      if (/failed to fetch|networkerror|load failed|network request failed/i.test(m)) {
        m += ` — Is the API running at ${API_BASE}? Install Python deps (\`pip install -r requirements.txt\`), ffmpeg on PATH, then use \`npm start\` and choose browser or Electron so the backend starts with the UI.`;
      }
      setErr(m);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }
  return (
    <>
      <div className="hero">
        <div>
          <p className="eyebrow">BEATMAPER LEARNED MODEL</p>
          <h1>
            ranked-map
            <br />
            pattern engine
          </h1>
          <p className="sub">
            Upload a song. The backend detects beats, loads the trained ranked
            pattern model, exports a Beat Saber ZIP, then previews the generated
            gameplay in Three.js.
          </p>
          <label className="upload">
            <input
              type="file"
              accept="audio/*,.wav,.mp3,.ogg"
              onChange={upload}
            />{" "}
            {busy ? "analyzing audio..." : "upload song"}
          </label>
          {err && <p className="err">Upload failed: {err}</p>}
        </div>
        <BeatViz beats={res?.analysis?.beats || []} />
      </div>
      <ControlPanel
        settings={settings}
        setSettings={setSettings}
        preset={preset}
        setPreset={setPreset}
      />
      {res && (
        <section className="panel">
          <h2>Generated map</h2>
          <div className="stats">
            <b>{Math.round(res.analysis?.bpm || 0)} BPM</b>
            <b>{Math.round(res.analysis?.duration || 0)} sec</b>
            <b>{res.stats?.notes ?? res.previewNotes?.length ?? 0} notes</b>
            <b>{res.stats?.walls ?? 0} walls</b>
            <b>{res.stats?.bombs || 0} bombs</b>
            <b>{res.modelLoaded ? "learned model" : "fallback"}</b>
            <b>{res.stats?.generator?.engine || "generator"}</b>
            <b>{res.stats?.generator?.dynamicSections || 0} dynamic sections</b>
            <b>{res.stats?.generator?.avgIntensity ?? "—"} avg intensity</b>
            <b>{res.stats?.generator?.stateGrid ?? "—"} beat grid</b>
            <b>{res.stats?.generator?.alignment ?? "—"} beat align</b>
            <b>{res.stats?.difficulties?.length || 1} difficulties</b>
            <b>{res.stats?.validation?.valid ? "valid map" : "check map"}</b>
            <b>{res.stats?.validation?.issues?.length || 0} issues</b>
            <b>{res.review?.score?.predictedFun ?? "—"} fun score</b>
            <b>
              {res.review?.score?.simulation?.missProbability ?? "—"} miss risk
            </b>
            <b>{res.audioFile || "song.egg"}</b>
          </div>
          <a className="download" href={API_BASE + res.download}>
            Download Beat Saber ZIP
          </a>
          {res.project && (
            <a
              className="download secondary"
              href={API_BASE + res.project}
              target="_blank"
            >
              Open internal project JSON
            </a>
          )}
          {res.projectGrid && (
            <a
              className="download secondary"
              href={API_BASE + res.projectGrid}
              target="_blank"
            >
              Open beat/grid view
            </a>
          )}
          <p className="path">Saved: {res.folder}</p>
          {res.review && (
            <div className="agentReport">
              {res.review.agents.map((a, i) => (
                <div key={i}>
                  <b>{a.agent}</b>
                  <span>{a.verdict}</span>
                  <small>{a.notes}</small>
                </div>
              ))}
            </div>
          )}
          {res.audioWarning && <p className="err">{res.audioWarning}</p>}
        </section>
      )}
      {res && <GameplayPreview res={res} />}
      <section className="panel">
        <h2>Preview note</h2>
        <p>
          The simulation is a visual preview, not the actual Beat Saber engine.
          The exported ZIP still contains the real <code>Info.dat</code>,{" "}
          <code>ExpertStandard.dat</code>, and <code>song.egg</code>.
        </p>
      </section>
    </>
  );
}
createRoot(document.getElementById("root")).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
