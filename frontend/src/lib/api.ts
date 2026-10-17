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

export interface GalleryFilter {
	location: 'all' | 'without' | 'with';
	type: 'all' | 'image' | 'video';
	camera: string | null;
	album: string | null;
	date_from: string | null;
	date_to: string | null;
	archived: boolean;
}

export interface MonthBucket {
	month: string; // YYYY-MM
	count: number;
}

export interface AssetItem {
	id: string;
	local_taken_at: string;
	type: 'IMAGE' | 'VIDEO' | string;
	file_name: string;
	has_location: boolean;
	width: number | null;
	height: number | null;
}

export interface FilterOptions {
	cameras: { value: string; make: string; model: string; count: number }[];
	albums: { id: string; name: string; count: number }[];
}

/** Query string for the gallery filter; default values are left out. */
export function filterQuery(filter: GalleryFilter, extra: Record<string, string> = {}): string {
	const params = new URLSearchParams(extra);
	if (filter.location !== 'all') params.set('location', filter.location);
	if (filter.type !== 'all') params.set('type', filter.type);
	if (filter.camera !== null) params.set('camera', filter.camera);
	if (filter.album) params.set('album', filter.album);
	if (filter.date_from) params.set('date_from', filter.date_from);
	if (filter.date_to) params.set('date_to', filter.date_to);
	if (filter.archived) params.set('archived', 'true');
	const query = params.toString();
	return query ? `?${query}` : '';
}

export const thumbnailUrl = (id: string, size: 'thumbnail' | 'preview' = 'thumbnail') =>
	`/api/assets/${id}/thumbnail?size=${size}`;

export const getMonths = (filter: GalleryFilter) =>
	request<MonthBucket[]>('GET', `/api/assets/months${filterQuery(filter)}`);
export const getMonthAssets = (month: string, filter: GalleryFilter) =>
	request<AssetItem[]>('GET', `/api/assets${filterQuery(filter, { month })}`);
export const getFilterOptions = () => request<FilterOptions>('GET', '/api/assets/filter-options');

export const getHealth = () => request<Health>('GET', '/api/health');
export const getLibrary = () => request<Library>('GET', '/api/library');
export const startSync = (full: boolean | null = null) =>
	request<Job>('POST', '/api/library/sync', { full });
export const login = (apiKey: string) =>
	request<Me>('POST', '/api/auth/login', { api_key: apiKey });
export const logout = () => request<void>('POST', '/api/auth/logout');
export const getMe = () => request<Me>('GET', '/api/auth/me');
