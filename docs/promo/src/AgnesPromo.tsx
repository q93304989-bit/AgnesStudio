import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, interpolate, Easing, spring, useVideoConfig } from "remotion";
import { BrandOpen } from "./scenes/BrandOpen";
import { ImageUIReveal } from "./scenes/ImageUIReveal";
import { VideoUIReveal } from "./scenes/VideoUIReveal";
import { GalleryStack } from "./scenes/GalleryStack";
import { Outro } from "./scenes/Outro";

// 镜头时间轴（帧 @ 30fps）
export const SHOTS = {
  brand:   { from: 0,   dur: 150 }, // 5.0s
  imageUI: { from: 150, dur: 210 }, // 7.0s
  videoUI: { from: 360, dur: 180 }, // 6.0s
  gallery: { from: 540, dur: 180 }, // 6.0s
  outro:   { from: 720, dur: 150 }, // 5.0s
  fade:    { from: 870, dur: 30 },  // 1.0s
} as const;

export const TOTAL_FRAMES = 900;

export const AgnesPromo: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#0a1028" }}>
      <Sequence from={SHOTS.brand.from} durationInFrames={SHOTS.brand.dur}>
        <BrandOpen />
      </Sequence>
      <Sequence from={SHOTS.imageUI.from} durationInFrames={SHOTS.imageUI.dur}>
        <ImageUIReveal />
      </Sequence>
      <Sequence from={SHOTS.videoUI.from} durationInFrames={SHOTS.videoUI.dur}>
        <VideoUIReveal />
      </Sequence>
      <Sequence from={SHOTS.gallery.from} durationInFrames={SHOTS.gallery.dur}>
        <GalleryStack />
      </Sequence>
      <Sequence from={SHOTS.outro.from} durationInFrames={SHOTS.outro.dur}>
        <Outro />
      </Sequence>
      <FadeOut startFrame={SHOTS.fade.from} />
    </AbsoluteFill>
  );
};

// 背景渐变层：全片铺底
export const Backdrop: React.FC = () => {
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(1200px 800px at 30% 20%, rgba(91, 233, 255, 0.18), transparent 60%), " +
            "radial-gradient(900px 700px at 75% 80%, rgba(124, 140, 255, 0.16), transparent 60%), " +
            "linear-gradient(135deg, #0a1028 0%, #1a1648 50%, #0a1028 100%)",
        }}
      />
      {/* 网格微光 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(rgba(91,233,255,0.06) 1px, transparent 1px), " +
            "linear-gradient(90deg, rgba(91,233,255,0.06) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          opacity: 0.4,
        }}
      />
    </AbsoluteFill>
  );
};

// 底部通栏字幕
export const Caption: React.FC<{ text: string; appearAt: number }> = ({ text, appearAt }) => {
  const frame = useCurrentFrame();
  const localFrame = Math.max(0, frame - appearAt);
  const opacity = interpolate(localFrame, [0, 18, 60, 90], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (frame < appearAt) return null;
  return (
    <div
      style={{
        position: "absolute",
        bottom: 60,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity,
      }}
    >
      <div
        style={{
          fontFamily: "Inter, system-ui, -apple-system, sans-serif",
          fontWeight: 500,
          fontSize: 28,
          letterSpacing: "0.12em",
          color: "#5be9ff",
          background: "rgba(10,16,40,0.6)",
          padding: "14px 36px",
          borderRadius: 999,
          border: "1px solid rgba(91,233,255,0.25)",
          backdropFilter: "blur(8px)",
        }}
      >
        {text}
      </div>
    </div>
  );
};

// 全片结尾淡出（黑场）
export const FadeOut: React.FC<{ startFrame: number }> = ({ startFrame }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [startFrame, startFrame + 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#0a1028", opacity }} />
  );
};