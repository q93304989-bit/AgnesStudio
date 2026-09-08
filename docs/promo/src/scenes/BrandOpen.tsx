import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, staticFile } from "remotion";
import { Backdrop } from "../AgnesPromo";

// 品牌开场：图标砸落 + 字标 + tagline
export const BrandOpen: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // icon drop-bounce: scale 0.3 -> 1.12 -> 1
  const iconScale = spring({
    frame,
    fps,
    config: { damping: 9, stiffness: 140, mass: 0.7 },
    durationInFrames: 45,
  });
  const iconFinalScale = interpolate(iconScale, [0, 1], [0.3, 1.12]);
  const iconShrink = frame < 28 ? 1 : interpolate(frame, [28, 35], [1.12, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const iconScaleFinal = frame < 28 ? iconFinalScale : iconFinalScale * iconShrink;

  // wordmark fade
  const wordOpacity = interpolate(frame, [40, 65], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const wordY = interpolate(frame, [40, 65], [20, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // tagline
  const tagOpacity = interpolate(frame, [75, 100], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const tagY = interpolate(frame, [75, 100], [16, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // 全片底层光晕呼吸
  const glow = interpolate(frame, [0, 150], [0.4, 0.85], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a1028" }}>
      <Backdrop />
      <div style={{
        position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <div style={{
          position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)",
          width: 600, height: 600, borderRadius: "50%",
          background: "radial-gradient(circle, rgba(91,233,255,0.55) 0%, transparent 60%)",
          opacity: glow,
          filter: "blur(20px)",
        }} />
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", transform: `scale(${iconScaleFinal})` }}>
          <img src={staticFile("textures/icon.png")}
               style={{ width: 260, height: 260, filter: "drop-shadow(0 0 40px rgba(91,233,255,0.7))" }} />
          <div style={{
            marginTop: 36, fontFamily: "Inter, system-ui, sans-serif", fontWeight: 800,
            fontSize: 96, color: "#f4f7ff", letterSpacing: "-0.02em",
            opacity: wordOpacity, transform: `translateY(${wordY}px)`,
            textShadow: "0 0 30px rgba(91,233,255,0.5)",
          }}>
            Agnes Studio
          </div>
          <div style={{
            marginTop: 18, fontFamily: "Inter, system-ui, sans-serif", fontWeight: 500,
            fontSize: 30, color: "#5be9ff", letterSpacing: "0.18em", textTransform: "uppercase",
            opacity: tagOpacity, transform: `translateY(${tagY}px)`,
          }}>
            a free multimodal playground
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};