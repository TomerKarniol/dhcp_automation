/**
 * Format a lease duration string like "8.00:00:00" into a human-readable string.
 * The format is D.HH:MM:SS where D is the number of days.
 */
export function formatLeaseDuration(duration: string | null): string {
  if (!duration) return "N/A";

  // Handle "D.HH:MM:SS" and "HH:MM:SS" formats
  const dotIndex = duration.indexOf(".");
  if (dotIndex !== -1) {
    const days = parseInt(duration.slice(0, dotIndex), 10);
    if (!isNaN(days)) {
      return days === 1 ? "1 day" : `${days} days`;
    }
  }

  // Fallback: return the raw value
  return duration;
}

/**
 * Convert a subnet mask string to its CIDR prefix length.
 * e.g. "255.255.255.0" → 24
 */
export function maskToCidr(mask: string): number {
  const octets = mask.split(".").map(Number);
  let bits = 0;
  for (const octet of octets) {
    let n = octet;
    while (n > 0) {
      bits += n & 1;
      n >>= 1;
    }
  }
  return bits;
}

/**
 * Format a scope ID with CIDR notation.
 * e.g. ("10.10.10.0", "255.255.255.0") → "10.10.10.0/24"
 */
export function formatScopeId(id: string, mask: string): string {
  const cidr = maskToCidr(mask);
  return `${id}/${cidr}`;
}
