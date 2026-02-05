import * as React from 'react';
import { cn } from '@/lib/utils';

interface SplitSliderProps {
  value: number; // 0-100, represents the first client's percentage
  onChange: (value: number) => void;
  leftLabel: string;
  rightLabel: string;
  leftColor: string;
  rightColor: string;
  disabled?: boolean;
  className?: string;
}

export const SplitSlider: React.FC<SplitSliderProps> = ({
  value,
  onChange,
  leftLabel,
  rightLabel,
  leftColor,
  rightColor,
  disabled = false,
  className,
}) => {
  const rightValue = 100 - value;

  return (
    <div className={cn('space-y-2', className)}>
      {/* Labels with percentages */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: leftColor }}
          />
          <span className="font-medium">{leftLabel}</span>
          <span className="text-muted-foreground">{value}%</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">{rightValue}%</span>
          <span className="font-medium">{rightLabel}</span>
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: rightColor }}
          />
        </div>
      </div>

      {/* Split bar visualization */}
      <div className="relative">
        <div className="h-4 rounded-lg overflow-hidden flex">
          <div
            className="h-full transition-all duration-150"
            style={{
              width: `${value}%`,
              backgroundColor: leftColor,
            }}
          />
          <div
            className="h-full transition-all duration-150"
            style={{
              width: `${rightValue}%`,
              backgroundColor: rightColor,
            }}
          />
        </div>

        {/* Slider input overlay */}
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={value}
          onChange={(e) => onChange(parseInt(e.target.value))}
          disabled={disabled}
          className={cn(
            'absolute inset-0 w-full h-full opacity-0 cursor-pointer',
            disabled && 'cursor-not-allowed'
          )}
        />

        {/* Thumb indicator */}
        <div
          className="absolute top-0 h-full w-1 bg-white/80 shadow-md transition-all duration-150 pointer-events-none"
          style={{ left: `calc(${value}% - 2px)` }}
        />
      </div>
    </div>
  );
};
