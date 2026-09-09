/**
 * Shared cross-component types.
 *
 * Keeping these in their own module avoids circular imports between
 * App.tsx and the sub-components in components/.
 */

export type ViewState = 'chat' | 'content';
