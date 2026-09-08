import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, staticFile, Img } from "remotion";
import { Backdrop, Caption } from "../AgnesPromo";

// 图片生成 UI 推入 + 按钮高亮
export const ImageUIReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 屏幕卡片从底部上推
  const cardY = spring({ frame, fps, config: { damping: 14, stiffness: 90, mass: 0.9 }, durationInFrames: 60 });
  const cardScale = interpolate(cardY, [0, 1], [0.7, 1]);

  // 提示词文本"打字"揭示
  const promptText = "A glowing floating city above a misty canyon at sunrise";
  const typed = Math.min(promptText.length, Math.floor((frame - 25) * 1.2));
  const shown = promptText.slice(0, Math.max(0, typed));

  // 按钮脉冲
  const btnPulse = interpolate(frame, [80, 110], [0.7, 1.0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a1028" }}>
      <Backdrop />
      <div style={{
        position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {/* 浏览器外壳 */}
        <div style={{
          width: 1240, height: 760, borderRadius: 22, overflow: "hidden",
          background: "#ffffff", boxShadow: "0 30px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(91,233,255,0.3)",
          transform: `translateY(${(1 - cardScale) * 80}px) scale(${cardScale})`,
          opacity: interpolate(cardY, [0, 0.3, 1], [0, 0.6, 1]),
        }}>
          <Img src={staticFile("textures/ui-image.png")}
               style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          {/* 提示词覆盖层 */}
          <div style={{
            position: "absolute", left: 70, top: 220, width: 480, height: 140,
            padding: 16, borderRadius: 12, background: "rgba(240,243,247,0.95)",
            border: "1px solid rgba(91,233,255,0.4)", backdropFilter: "blur(6px)",
            display: "flex", alignItems: "center",
            fontFamily: "Inter, sans-serif", fontSize: 20, color: "#1f2937",
          }}>
            <span style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 16, color: "#374151" }}>
              {shown || ""}
              <span style={{ display: "inline-block", width: 2, height: 22, background: "#5be9ff", marginLeft: 2,
                             opacity: (frame % 30 < 15) ? 1 : 0 }} />
            </span>
          </div>
          {/* 按钮高亮 */}
          <div style={{
            position: "absolute", left: 80, top: 640, padding: "16px 32px", borderRadius: 12,
            background: "#3b82f6", color: "#fff", fontFamily: "Inter, sans-serif", fontWeight: 600, fontSize: 22,
            boxShadow: `0 0 ${btnPulse * 30}px rgba(91,233,255,${btnPulse})`,
          }}>
            🚀 Start generating
          </div>
        </div>
        {/* 浮动提示气泡 */}
        <div style={{
          position: "absolute", right: 200, top: 180, padding: "10px 18px", borderRadius: 999,
          background: "rgba(91,233,255,0.15)", border: "1px solid rgba(91,233,255,0.5)",
          color: "#5be9ff", fontFamily: "Inter, sans-serif", fontWeight: 600, fontSize: 18,
          opacity: interpolate(frame, [60, 80], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          transform: `translateX(${interpolate(frame, [60, 80], [20, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px)`,
        }}>
          text → image in 5s
        </div>
      </div>
      <Caption text="Text → Image · 文生图" appearAt={20} />
      <Caption text="Type a prompt, get a picture" appearAt={140} />
    </AbsoluteFill>
  );
};