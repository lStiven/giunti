/** Admin panel API (`/api/v1/admin`): every call needs an administrator key. */
import { API_KEY_HEADER, API_URL, invalidResponse, readJson, send } from "../api/client";

export interface ClientView {
  id: string;
  name: string;
  active: boolean;
  is_admin: boolean;
  per_minute_limit: number;
  daily_limit: number;
  used_today: number;
  created_at: string;
  key_created_at: string;
  last_used_at: string | null;
}

export interface IssuedKey {
  client: ClientView;
  /** Shown only once: the server keeps only its hash. */
  api_key: string;
  invite_url: string;
}

export interface NewClient {
  name: string;
  daily_limit: number;
  per_minute_limit: number;
}

export type ClientChanges = Partial<
  Pick<ClientView, "name" | "active" | "daily_limit" | "per_minute_limit">
>;

const ADMIN_URL = `${API_URL}/api/v1/admin`;

export async function listClients(adminKey: string): Promise<ClientView[]> {
  const body = await call(adminKey, "/clients");
  if (!Array.isArray(body) || !body.every(isClientView)) {
    throw invalidResponse(new Response());
  }
  return body;
}

export async function createClient(adminKey: string, client: NewClient): Promise<IssuedKey> {
  return issued(await call(adminKey, "/clients", "POST", client));
}

export async function updateClient(
  adminKey: string,
  clientId: string,
  changes: ClientChanges,
): Promise<ClientView> {
  const body = await call(adminKey, `/clients/${encodeURIComponent(clientId)}`, "PATCH", changes);
  if (!isClientView(body)) {
    throw invalidResponse(new Response());
  }
  return body;
}

export async function replaceKey(adminKey: string, clientId: string): Promise<IssuedKey> {
  return issued(await call(adminKey, `/clients/${encodeURIComponent(clientId)}/key`, "POST"));
}

async function call(
  adminKey: string,
  path: string,
  method = "GET",
  body?: object,
): Promise<unknown> {
  const headers: Record<string, string> = { [API_KEY_HEADER]: adminKey };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const response = await send(`${ADMIN_URL}${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return readJson(response);
}

function issued(body: unknown): IssuedKey {
  if (
    !isRecord(body) ||
    !isClientView(body["client"]) ||
    typeof body["api_key"] !== "string" ||
    typeof body["invite_url"] !== "string"
  ) {
    throw invalidResponse(new Response());
  }
  return { client: body["client"], api_key: body["api_key"], invite_url: body["invite_url"] };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isClientView(value: unknown): value is ClientView {
  return (
    isRecord(value) &&
    typeof value["id"] === "string" &&
    typeof value["name"] === "string" &&
    typeof value["active"] === "boolean" &&
    typeof value["is_admin"] === "boolean" &&
    typeof value["per_minute_limit"] === "number" &&
    typeof value["daily_limit"] === "number" &&
    typeof value["used_today"] === "number" &&
    typeof value["created_at"] === "string" &&
    typeof value["key_created_at"] === "string" &&
    (value["last_used_at"] === null || typeof value["last_used_at"] === "string")
  );
}
