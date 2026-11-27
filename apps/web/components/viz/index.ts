/**
 * The site's charts and figures. Each part is a server component, drawn as
 * plain HTML and SVG, except the chart's crosshair, which is a small client
 * part inside LineChart. Their arithmetic and words live in lib/viz.ts and
 * lib/copy.ts (`viz`).
 */
export { ChanceReadout } from "./ChanceReadout";
export { LineChart } from "./LineChart";
export { MarginBars } from "./MarginBars";
export { MoveScale, MoveTrack, MoveWindows } from "./MoveTrack";
export { RangeBar } from "./RangeBar";
export { PickFigures, SlipFiguresView as SlipFigures } from "./SlipFigures";
export { Sparkline } from "./Sparkline";
export { SplitBar } from "./SplitBar";
