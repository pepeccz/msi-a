import { decodeJwt } from "jose";

export interface JwtPayload {
  sub?: string;
  exp?: number;
  iat?: number;
  role?: string;
  [key: string]: unknown;
}

const CLOCK_SKEW_SECONDS = 30;

export function decodeToken(token: string): JwtPayload | null {
  try {
    return decodeJwt(token) as JwtPayload;
  } catch {
    return null;
  }
}

export function getTokenExpiration(token: string): number | null {
  const payload = decodeToken(token);
  if (!payload?.exp) return null;
  return payload.exp * 1000;
}

export function isTokenExpired(token: string | null | undefined): boolean {
  if (!token) return true;
  const payload = decodeToken(token);
  if (!payload?.exp) return true;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return payload.exp <= nowSeconds + CLOCK_SKEW_SECONDS;
}

export function getTokenRole(token: string | null | undefined): string | null {
  if (!token) return null;
  const payload = decodeToken(token);
  return typeof payload?.role === "string" ? payload.role : null;
}
