import React, { useEffect, useRef } from 'react';

interface VoiceVisualizerProps {
  state: 'idle' | 'listening' | 'thinking' | 'speaking';
  audioLevel: number;
}

export const VoiceVisualizer: React.FC<VoiceVisualizerProps> = ({ state, audioLevel }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let phase = 0;

    const render = () => {
      phase += 0.04;
      const width = canvas.width;
      const height = canvas.height;
      const centerX = width / 2;
      const centerY = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Base radius and dynamic amplitude based on state and audio level
      let baseRadius = 80;
      let waveCount = 4;
      let colorPrimary = 'rgba(16, 185, 129, '; // emerald
      let colorSecondary = 'rgba(6, 182, 212, '; // cyan

      if (state === 'idle') {
        baseRadius = 70;
        waveCount = 2;
        colorPrimary = 'rgba(100, 116, 139, ';
        colorSecondary = 'rgba(71, 85, 105, ';
      } else if (state === 'thinking') {
        baseRadius = 75;
        waveCount = 5;
        colorPrimary = 'rgba(168, 85, 247, '; // purple
        colorSecondary = 'rgba(236, 72, 153, '; // pink
      } else if (state === 'speaking') {
        baseRadius = 85;
        waveCount = 6;
        colorPrimary = 'rgba(59, 130, 246, '; // blue
        colorSecondary = 'rgba(147, 51, 234, '; // violet
      }

      const activeFactor = state === 'idle' ? 0.05 : Math.max(0.15, audioLevel * 1.4);

      // Draw background ambient glow
      const radialGradient = ctx.createRadialGradient(
        centerX, centerY, 10,
        centerX, centerY, baseRadius * 2.2
      );
      radialGradient.addColorStop(0, colorPrimary + (0.25 * activeFactor + 0.1) + ')');
      radialGradient.addColorStop(1, 'rgba(15, 23, 42, 0)');
      ctx.fillStyle = radialGradient;
      ctx.beginPath();
      ctx.arc(centerX, centerY, baseRadius * 2.2, 0, Math.PI * 2);
      ctx.fill();

      // Draw pulsating harmonic organic waves
      for (let i = 0; i < waveCount; i++) {
        ctx.beginPath();
        const wavePhase = phase + (i * Math.PI) / waveCount;
        const currentRadius = baseRadius + i * 8 + Math.sin(wavePhase * 2) * (15 * activeFactor);

        for (let angle = 0; angle < Math.PI * 2; angle += 0.05) {
          const distortion = Math.sin(angle * (3 + i) + wavePhase * 3) * (20 * activeFactor);
          const r = currentRadius + distortion;
          const x = centerX + Math.cos(angle) * r;
          const y = centerY + Math.sin(angle) * r;

          if (angle === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }

        ctx.closePath();
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = (i % 2 === 0 ? colorPrimary : colorSecondary) + (0.7 - i * 0.1) + ')';
        ctx.stroke();
      }

      // Draw solid central glowing sphere
      const coreGradient = ctx.createRadialGradient(
        centerX - 15, centerY - 15, 5,
        centerX, centerY, baseRadius
      );
      coreGradient.addColorStop(0, '#ffffff');
      coreGradient.addColorStop(0.3, colorPrimary + '0.9)');
      coreGradient.addColorStop(1, colorSecondary + '0.6)');

      ctx.beginPath();
      ctx.arc(centerX, centerY, baseRadius * (1 + activeFactor * 0.2), 0, Math.PI * 2);
      ctx.fillStyle = coreGradient;
      ctx.fill();

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [state, audioLevel]);

  return (
    <div className="relative flex items-center justify-center">
      <canvas
        ref={canvasRef}
        width={340}
        height={340}
        className="relative z-10 transition-transform duration-300 transform"
      />
    </div>
  );
};