import { Component, lazy, Suspense, useEffect, useRef, useState } from 'react'

const OracleCanvas = lazy(() => import('@react-three/fiber').then(({ Canvas, useFrame }) => {
  function Relic() {
    const orb = useRef(null)
    const ring = useRef(null)
    const nodes = useRef(null)

    useFrame(({ clock }) => {
      const time = clock.getElapsedTime()
      if (orb.current) orb.current.rotation.y = time * 0.12
      if (ring.current) ring.current.rotation.z = time * 0.08
      if (nodes.current) nodes.current.rotation.z = -time * 0.05
    })

    const points = [[-1.08, 0.28, 0], [0.9, 0.52, 0], [0.58, -0.7, 0], [-0.7, -0.52, 0]]

    return <>
      <mesh ref={ring} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.04, 0.018, 8, 64]} />
        <meshBasicMaterial color="#a88bd6" transparent opacity={0.62} />
      </mesh>
      <mesh ref={orb}>
        <icosahedronGeometry args={[0.42, 1]} />
        <meshStandardMaterial color="#b88c52" emissive="#5c3e1e" emissiveIntensity={0.6} roughness={0.56} metalness={0.72} />
      </mesh>
      <group ref={nodes}>
        {points.map(([x, y, z], index) => <mesh key={index} position={[x, y, z]}>
          <sphereGeometry args={[index === 0 ? 0.065 : 0.045, 8, 8]} />
          <meshBasicMaterial color={index === 0 ? '#d8ad68' : '#78b9cf'} />
        </mesh>)}
      </group>
    </>
  }

  function Scene() {
    return <Canvas
      dpr={[1, 1.5]}
      camera={{ position: [0, 0, 3.6], fov: 34 }}
      gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}
      fallback={<span className="oracle-lens-fallback-label">WEBGL OFFLINE</span>}
    >
      <ambientLight intensity={0.45} />
      <pointLight position={[1.6, 1.8, 2.6]} intensity={1.8} color="#d8ad68" />
      <pointLight position={[-1.8, -1.2, 1.8]} intensity={1.1} color="#78b9cf" />
      <Relic />
    </Canvas>
  }

  return { default: Scene }
}))

class SceneBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches)

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(query.matches)
    update()
    query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])

  return reduced
}

export function OracleLens() {
  const reducedMotion = useReducedMotion()
  const [webgl] = useState(() => {
    if (typeof document === 'undefined') return false
    try {
      const canvas = document.createElement('canvas')
      return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    } catch {
      return false
    }
  })
  const useCanvas = !reducedMotion && webgl

  return <aside className={`oracle-lens${reducedMotion || !webgl ? ' oracle-lens-static' : ''}`} aria-hidden="true">
    <div className="oracle-lens-frame">
      <div className="oracle-lens-fallback" aria-hidden="true">
        <i className="oracle-lens-core" />
        <i className="oracle-lens-orbit oracle-lens-orbit-one" />
        <i className="oracle-lens-orbit oracle-lens-orbit-two" />
        <i className="oracle-lens-node oracle-lens-node-one" />
        <i className="oracle-lens-node oracle-lens-node-two" />
        <i className="oracle-lens-node oracle-lens-node-three" />
      </div>
      {useCanvas && <SceneBoundary><Suspense fallback={null}><OracleCanvas /></Suspense></SceneBoundary>}
    </div>
    <span className="oracle-lens-label">ORACLE / CAPITAL SIGNAL</span>
  </aside>
}
