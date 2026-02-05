import * as React from "react"

import { cn } from "@/lib/utils"

interface SliderProps {
  value: number[];
  onValueChange: (value: number[]) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  className?: string;
}

const Slider = React.forwardRef<
  HTMLInputElement,
  SliderProps
>(({ value, onValueChange, min = 0, max = 100, step = 1, disabled, className }, ref) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onValueChange([parseInt(e.target.value)]);
  };

  return (
    <input
      ref={ref}
      type="range"
      min={min}
      max={max}
      step={step}
      value={value[0]}
      onChange={handleChange}
      disabled={disabled}
      className={cn(
        "w-full h-2 bg-secondary rounded-lg appearance-none cursor-pointer",
        "[&::-webkit-slider-thumb]:appearance-none",
        "[&::-webkit-slider-thumb]:w-4",
        "[&::-webkit-slider-thumb]:h-4",
        "[&::-webkit-slider-thumb]:rounded-full",
        "[&::-webkit-slider-thumb]:bg-primary",
        "[&::-webkit-slider-thumb]:cursor-pointer",
        "[&::-webkit-slider-thumb]:shadow-md",
        "[&::-webkit-slider-thumb]:transition-transform",
        "[&::-webkit-slider-thumb]:hover:scale-110",
        "[&::-moz-range-thumb]:w-4",
        "[&::-moz-range-thumb]:h-4",
        "[&::-moz-range-thumb]:rounded-full",
        "[&::-moz-range-thumb]:bg-primary",
        "[&::-moz-range-thumb]:cursor-pointer",
        "[&::-moz-range-thumb]:border-0",
        "[&::-moz-range-thumb]:shadow-md",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        className
      )}
    />
  )
})
Slider.displayName = "Slider"

export { Slider }
