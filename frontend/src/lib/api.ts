// SPDX-License-Identifier: AGPL-3.0-or-later
// Typed client for the core API. Mirrors the Pydantic models in core/src/steward/api.

/** Error returned by the core: a machine-readable code plus parameters for the message. */
export class ApiError extends Error {
	constructor(
		readonly status: number,
		readonly code: string,
		readonly params: Record<string, unknown> = {}
	) {
		super(code);
	}
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
	let response: Response;
	try {
		response = await fetch(path, {
			method,
			headers: body === undefined ? {} : { 'content-type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body)
		});
	} catch {
		throw new ApiError(0, 'core_unreachable');
	}
	if (response.status === 204) return undefined as T;
	const data = await response.json().catch(() => null);
	if (!response.ok) {
		throw new ApiError(response.status, data?.code ?? 'unexpected_error', data?.params ?? {});
	}
	return data as T;
}

export interface DatabaseHealth {
	ok: boolean;
	server_version: string | null;
	pgvector_version: string | null;
	/** Machine-readable error code; translated by the UI. */
	error: string | null;
}

export interface ImmichHealth {
	configured: boolean;
	reachable: boolean;
	version: string | null;
	supported: boolean | null;
}

export interface Health {
	status: 'ok' | 'degraded';
	version: string;
	database: DatabaseHealth;
	immich: ImmichHealth;
}

export interface Me {
	id: string;
	name: string;
	email: string;
}

export interface Job {
	id: string;
	kind: string;
	status: 'queued' | 'running' | 'done' | 'failed';
	progress: Record<string, unknown>;
	/** Error code, translated by the UI. */
	error: string | null;
	created_at: string;
	started_at: string | null;
	finished_at: string | null;
}

export interface Library {
	assets: number;
	videos: number;
	with_gps: number;
	without_gps: number;
	albums: number;
	synced_at: string | null;
	full_synced_at: string | null;
	sync_job: Job | null;
}

export const isActive = (job: Job | null) =>
	job !== null && (job.status === 'queued' || job.status === 'running');

export const getHealth = () => request<Health>('GET', '/api/health');
export const getLibrary = () => request<Library>('GET', '/api/library');
export const startSync = (full: boolean | null = null) =>
	request<Job>('POST', '/api/library/sync', { full });
export const login = (apiKey: string) =>
	request<Me>('POST', '/api/auth/login', { api_key: apiKey });
export const logout = () => request<void>('POST', '/api/auth/logout');
export const getMe = () => request<Me>('GET', '/api/auth/me');
