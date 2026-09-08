import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, staticFile, Img } from "remotion";
import { Backdrop, Caption } from "../AgnesPromo";

// 三联拼图：list-stack-press — 3 张样本错落入场
const SAMPLES = [
  { src: "textures/ui-image.png", tag: "Image",  color: "#5be9ff" },
  { src: "textures/ui-video.png", tag: "Video",  color: "#7c8cff" },
  { src: "textures/icon.png",     tag: "Icon",   color: "#f4f7ff" },
];

export const GalleryStack: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a1028" }}>
      <Backdrop />
      <div style={{
        position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", gap: 60,
      }}>
        {SAMPLES.map((s, i) => {
          const delay = i * 12;
          const y = spring({ frame: frame - delay, fps, config: { damping: 12, stiffness: 110, mass: 0.9 }, durationInFrames: 50 });
          const scale = interpolate(y, [0, 1], [0.6, 1]);
          const opacity = interpolate(y, [0, 0.4, 1], [0, 0.7, 1]);
          return (
            <div key={i} style={{
              width: 380, height: 480, borderRadius: 22, overflow: "hidden",
              background: "#fff", boxShadow: `0 24px 60px rgba(0,0,0,0.45), 0 0 0 2px ${s.color}55`,
              transform: `translateY(${(1 - y) * 80}px) scale(${scale}) rotate(${(i - 1) * 4}deg)`,
              position: "relative",
              opacity,
            }}>
              <Img src={staticFile(s.src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              <div style={{
                position: "absolute", left: 18, top: 18, padding: "6px 14px", borderRadius: 999,
                background: s.color, color: "#0a1028",
                fontFamily: "Inter, sans-serif", fontWeight: 700, fontSize: 16, letterSpacing: "0.06em",
              }}>
                {s.tag.toUpperCase()}
              </div>
            </div>
          );
        })}
      </div>
      <Caption text="Every prompt saved · 历史自动落盘" appearAt={30} />
      <Caption text="Reuse parameters · 一键复用参数" appearAt={120} />
    </AbsoluteFill>
  );
};