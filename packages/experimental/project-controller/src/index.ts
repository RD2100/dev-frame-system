/**
 * Package entry for the project controller. The default export is the
 * {@link ProjectController} Cordis service the Loader mounts; the named
 * exports carry the request shapes, the domain spec, and the stable error
 * type. The service registers as `ctx.projectController`.
 * @module @deepseek-ai/dsh-experimental-project-controller
 */

export { ProjectControllerError } from './errors.ts'
export type { ProjectControllerErrorCode } from './errors.ts'
export { projectTasksDomainSpec, taskRecordSchema } from './spec.ts'
export { ProjectController } from './controller.ts'
export type { MainTreeMergeMarker, ProjectControllerConfig, TaskBlockDetail } from './controller.ts'
export { ProjectController as default } from './controller.ts'
