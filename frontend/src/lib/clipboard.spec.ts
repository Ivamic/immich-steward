// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from 'vitest';
import { copyText } from './clipboard';

/** A minimal document: the hidden field and execCommand. */
function fakeDocument(execResult: boolean | 'throws') {
	const field = {
		value: '',
		style: {} as Record<string, string>,
		setAttribute: vi.fn(),
		select: vi.fn(),
		remove: vi.fn()
	};
	const doc = {
		createElement: vi.fn(() => field),
		body: { append: vi.fn() },
		activeElement: { focus: vi.fn() },
		execCommand: vi.fn(() => {
			if (execResult === 'throws') throw new Error('not allowed');
			return execResult;
		})
	};
	vi.stubGlobal('document', doc);
	return { doc, field };
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('copyText', () => {
	it('uses the clipboard API on a secure page', async () => {
		const writeText = vi.fn(() => Promise.resolve());
		vi.stubGlobal('isSecureContext', true);
		vi.stubGlobal('navigator', { clipboard: { writeText } });
		const { doc } = fakeDocument(true);

		expect(await copyText('42.4, 19.26')).toBe(true);
		expect(writeText).toHaveBeenCalledWith('42.4, 19.26');
		expect(doc.execCommand).not.toHaveBeenCalled();
	});

	it('falls back to execCommand over plain HTTP', async () => {
		vi.stubGlobal('isSecureContext', false);
		vi.stubGlobal('navigator', {});
		const { doc, field } = fakeDocument(true);

		expect(await copyText('42.4, 19.26')).toBe(true);
		expect(field.value).toBe('42.4, 19.26');
		expect(field.select).toHaveBeenCalled();
		expect(doc.execCommand).toHaveBeenCalledWith('copy');
		expect(field.remove).toHaveBeenCalled();
		expect(doc.activeElement.focus).toHaveBeenCalled();
	});

	it('falls back when the clipboard API refuses', async () => {
		vi.stubGlobal('isSecureContext', true);
		vi.stubGlobal('navigator', {
			clipboard: { writeText: () => Promise.reject(new Error('denied')) }
		});
		const { doc } = fakeDocument(true);

		expect(await copyText('x')).toBe(true);
		expect(doc.execCommand).toHaveBeenCalledWith('copy');
	});

	it.each([false, 'throws' as const])(
		'reports failure when execCommand gives %s',
		async (result) => {
			vi.stubGlobal('isSecureContext', false);
			vi.stubGlobal('navigator', {});
			const { field } = fakeDocument(result);

			expect(await copyText('x')).toBe(false);
			expect(field.remove).toHaveBeenCalled();
		}
	);
});
