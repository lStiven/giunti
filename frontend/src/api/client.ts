/**
 * API client for `POST /api/v1/questionnaires` (multipart file + `X-API-Key` header).
 * Must handle `ApiError` responses, 429 with `Retry-After`, and multi-minute processing times.
 */
export const API_URL: string = import.meta.env.VITE_API_URL ?? "";
