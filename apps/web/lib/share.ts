export async function shareInviteLink(
  link: string,
  text: string,
): Promise<"shared" | "copied"> {
  try {
    const { default: WebApp } = await import("@twa-dev/sdk");
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
    WebApp.openTelegramLink(shareUrl);
    return "shared";
  } catch {
    await navigator.clipboard.writeText(link);
    return "copied";
  }
}
