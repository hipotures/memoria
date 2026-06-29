import type { AtlasLevel } from "../state/atlasReducer";

type RegionVisualTreatmentInput = {
  level: AtlasLevel;
  isSelected: boolean;
  isDimmed: boolean;
  index: number;
  hasActiveSelection: boolean;
};

type RegionVisualTreatment = {
  fillAlpha: number;
  strokeAlpha: number;
  strokeWidth: number;
  showLabel: boolean;
  showCountLabel: boolean;
  showCentroid: boolean;
  centroidRadius: number;
  centroidAlpha: number;
  labelAlpha: number;
  countAlpha: number;
  labelFontSize: number;
};

export function presentRegionVisualTreatment({
  level,
  isSelected,
  isDimmed,
  index,
  hasActiveSelection,
}: RegionVisualTreatmentInput): RegionVisualTreatment {
  if (level === "overview") {
    return {
      fillAlpha: isDimmed ? 0.14 : isSelected ? 0.36 : 0.2,
      strokeAlpha: isSelected ? 0.88 : isDimmed ? 0.22 : 0.54,
      strokeWidth: isSelected ? 4 : 2,
      showLabel: true,
      showCountLabel: true,
      showCentroid: false,
      centroidRadius: 0,
      centroidAlpha: 0,
      labelAlpha: isDimmed ? 0.46 : 1,
      countAlpha: isDimmed ? 0.62 : 1,
      labelFontSize: isSelected ? 19 : 17,
    };
  }

  if (isSelected) {
    return {
      fillAlpha: 0.18,
      strokeAlpha: 0.88,
      strokeWidth: 3.5,
      showLabel: true,
      showCountLabel: true,
      showCentroid: false,
      centroidRadius: 0,
      centroidAlpha: 0,
      labelAlpha: 1,
      countAlpha: 1,
      labelFontSize: 19,
    };
  }

  if (!hasActiveSelection) {
    return {
      fillAlpha: isDimmed ? 0.03 : index < 4 ? 0.1 : 0.08,
      strokeAlpha: isDimmed ? 0.16 : 0.4,
      strokeWidth: isDimmed ? 1 : 2,
      showLabel: !isDimmed,
      showCountLabel: !isDimmed,
      showCentroid: false,
      centroidRadius: 0,
      centroidAlpha: 0,
      labelAlpha: isDimmed ? 0.34 : 0.92,
      countAlpha: isDimmed ? 0.28 : 0.82,
      labelFontSize: 17,
    };
  }

  const showLabel = !isDimmed && index < 2;
  const showCountLabel = showLabel;

  return {
    fillAlpha: 0,
    strokeAlpha: isDimmed ? 0.12 : 0.22,
    strokeWidth: isDimmed ? 1 : 1.5,
    showLabel,
    showCountLabel,
    showCentroid: true,
    centroidRadius: 5,
    centroidAlpha: isDimmed ? 0.16 : 0.5,
    labelAlpha: isDimmed ? 0.34 : 0.74,
    countAlpha: isDimmed ? 0.28 : 0.58,
    labelFontSize: 16,
  };
}
