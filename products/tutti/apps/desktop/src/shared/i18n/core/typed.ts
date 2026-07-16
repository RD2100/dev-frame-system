import type { en } from "../locales/en.ts";

type Primitive = string | number | boolean | bigint | symbol | null | undefined;
type StringKey<T> = Extract<keyof T, string>;

type NestedLeafPaths<T> = {
  [Key in StringKey<T>]: T[Key] extends Primitive
    ? Key
    : T[Key] extends readonly unknown[]
      ? Key
      : `${Key}.${NestedLeafPaths<T[Key]>}`;
}[StringKey<T>];

export type DesktopI18nKey = NestedLeafPaths<typeof en>;

export type I18nParams = Record<
  string,
  string | number | boolean | null | undefined
>;
