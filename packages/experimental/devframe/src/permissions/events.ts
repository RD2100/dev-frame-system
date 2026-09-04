/**
 * Compatibility name for the canonical persisted role-policy payload.
 *
 * The event declaration and runtime validation live in `../events.ts`; this
 * module remains a type-only entry so permission consumers do not create a
 * second `SessionEventMap` declaration for the same event type.
 */
export type { DevFrameRolePolicyEventData as DevFrameRolePolicyEvent } from '../events.ts'
