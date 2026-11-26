import { landing } from "@/lib/content";
import { OG_CONTENT_TYPE, OG_SIZE, previewImage } from "@/lib/og";

export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const alt = landing.headline;

export default function Image() {
  return previewImage({ title: landing.headline, kicker: landing.eyebrow });
}
