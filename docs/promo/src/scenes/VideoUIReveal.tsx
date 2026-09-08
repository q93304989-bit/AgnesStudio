import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, staticFile, Img } from "remotion";
import { Backdrop, Caption } from "../AgnesPromo";

// 视频生成 UI 转场：FlashCut 暖白闪 + 屏幕横移
export const VideoUIReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // FlashCut 0-8 帧
  const flash = interpolate(frame, [0, 4, 12], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // UI 横移入
  const cardX = spring({ frame: frame - 12, fps, config: { damping: 16, stiffness: 80, mass: 1 }, durationInFrames: 50 });
  const cardScale = interpolate(cardX, [0, 1], [0.92, 1]);

  // 进度条
  const progress = interpolate(frame, [50, 150], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a1028" }}>
      <Backdrop />
      <div style={{
        position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {/* FlashCut 闪白 */}
        <AbsoluteFill style={{
          background: "#fff", opacity: flash,
        }} />
        {/* 浏览器外壳 */}
        <div style={{
          width: 1240, height: 760, borderRadius: 22, overflow: "hidden",
          background: "#ffffff", boxShadow: "0 30px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(124,140,255,0.4)",
          transform: `translateX(${(1 - cardX) * 200}px) scale(${cardScale})`,
          opacity: interpolate(cardX, [0, 0.4, 1], [0, 0.7, 1]),
        }}>
          <Img src={staticFile("textures/ui-video.png")}
               style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          {/* 进度条覆盖 */}
          <div style={{
            position: "absolute", left: 80, top: 700, width: 1080, height: 12, borderRadius: 6,
            background: "rgba(0,0,0,0.06)", overflow: "hidden",
          }}>
            <div style={{
              width: `${progress * 100}%`, height: "100%",
              background: "linear-gradient(90deg, #5be9ff, #7c8cff)",
              boxShadow: "0 0 18px rgba(91,233,255,0.7)",
            }} />
          </div>
          <div style={{
            position: "absolute", left: 80, top: 720, fontFamily: "ui-monospace, monospace",
            color: "#1f2937", fontSize: 16,
          }}>
            Rendering video · {Math.floor(progress * 100)}%
          </div>
        </div>
        {/* 视频标签 */}
        <div style={{
          position: "absolute", left: 200, top: 180, padding: "10px 18px", borderRadius: 999,
          background: "rgba(124,140,255,0.18)", border: "1px solid rgba(124,140,255,0.6)",
          color: "#7c8cff", fontFamily: "Inter, sans-serif", fontWeight: 700, fontSize: 20,
          opacity: interpolate(frame, [40, 55], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}>
          ▶ async · 4-12s · 720P
        </div>
      </div>
      <Caption text="Async video pipeline · 异步视频任务" appearAt={20} />
      <Caption text="Real progress, real files" appearAt={130} />
    </AbsoluteFill>
  );
};