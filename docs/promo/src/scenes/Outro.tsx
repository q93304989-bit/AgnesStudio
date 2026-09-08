import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, staticFile } from "remotion";
import { Backdrop } from "../AgnesPromo";

// Outro：字标 + tagline + GitHub 链接，1s hold
export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({ frame, fps, config: { damping: 14, stiffness: 100, mass: 0.9 }, durationInFrames: 60 });
  const tagOpacity = interpolate(frame, [40, 65], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const linkOpacity = interpolate(frame, [70, 95], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const linkY = interpolate(frame, [70, 95], [12, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a1028" }}>
      <Backdrop />
      <div style={{
        position: "absolute", inset: 0, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
      }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 28,
          transform: `scale(${interpolate(scale, [0, 1], [0.7, 1])})`,
          opacity: interpolate(scale, [0, 0.4, 1], [0, 0.7, 1]),
        }}>
          <img src={staticFile("textures/icon.png")}
               style={{ width: 140, height: 140, filter: "drop-shadow(0 0 40px rgba(91,233,255,0.6))" }} />
          <div style={{
            fontFamily: "Inter, sans-serif", fontWeight: 800, fontSize: 120, color: "#f4f7ff",
            letterSpacing: "-0.02em", textShadow: "0 0 30px rgba(91,233,255,0.4)",
          }}>
            Agnes Studio
          </div>
        </div>
        <div style={{
          marginTop: 32, fontFamily: "Inter, sans-serif", fontWeight: 600, fontSize: 36,
          color: "#5be9ff", letterSpacing: "0.06em",
          opacity: tagOpacity,
        }}>
          A free multimodal playground for students
        </div>
        <div style={{
          marginTop: 14, fontFamily: "Inter, sans-serif", fontWeight: 400, fontSize: 24,
          color: "#9ba6c4", letterSpacing: "0.04em",
          opacity: tagOpacity,
        }}>
          为学生而生 · 文生图与文生视频 · 开源
        </div>
        <div style={{
          marginTop: 56, padding: "16px 36px", borderRadius: 999,
          background: "rgba(91,233,255,0.1)", border: "1px solid rgba(91,233,255,0.5)",
          color: "#5be9ff", fontFamily: "ui-monospace, Menlo, monospace", fontWeight: 500, fontSize: 26,
          opacity: linkOpacity, transform: `translateY(${linkY}px)`,
        }}>
          github.com/q93304989-bit/AgnesStudio
        </div>
      </div>
    </AbsoluteFill>
  );
};