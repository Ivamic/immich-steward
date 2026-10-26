// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { foldText, matches } from './search';

describe('matches', () => {
	it.each([
		['Canon EOS 300D', 'eos', true],
		['Canon EOS 300D', 'CANON', true],
		['Canon EOS 300D', '300', true],
		['Canon EOS 300D', 'nikon', false],
		['Žabljak 2023', 'zab', true],
		['Ёжик в тумане', 'ежик', true],
		['Ёжик в тумане', 'ЁЖИК', true],
		['Côte d’Azur', 'cote', true],
		['Summer in Kotor', 'kotor summer', true],
		['Summer in Kotor', 'kotor winter', false],
		['anything', '', true],
		['anything', '   ', true]
	])('%s ~ %s', (name, query, expected) => {
		expect(matches(name, query)).toBe(expected);
	});

	it('folds case and accents', () => {
		expect(foldText('ŽÁÑÖ Ё')).toBe('zano е');
	});
});
