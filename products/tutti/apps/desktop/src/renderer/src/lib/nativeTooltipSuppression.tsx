import { useEffect } from "react";

const NATIVE_TITLE_ATTRIBUTE = "title";
const PRESERVED_NATIVE_TITLE_ATTRIBUTE = "data-native-title";

type TitleElement = Element & {
  getAttribute(name: string): string | null;
  removeAttribute(name: string): void;
  setAttribute(name: string, value: string): void;
};

const suppressNativeTooltip = (element: TitleElement) => {
  const title = element.getAttribute(NATIVE_TITLE_ATTRIBUTE);

  if (!title) {
    element.removeAttribute(NATIVE_TITLE_ATTRIBUTE);
    return;
  }

  if (!element.getAttribute(PRESERVED_NATIVE_TITLE_ATTRIBUTE)) {
    element.setAttribute(PRESERVED_NATIVE_TITLE_ATTRIBUTE, title);
  }

  element.removeAttribute(NATIVE_TITLE_ATTRIBUTE);
};

const suppressNativeTooltipsIn = (root: ParentNode) => {
  if (root instanceof Element && root.hasAttribute(NATIVE_TITLE_ATTRIBUTE)) {
    suppressNativeTooltip(root);
  }

  root.querySelectorAll(`[${NATIVE_TITLE_ATTRIBUTE}]`).forEach((element) => {
    suppressNativeTooltip(element);
  });
};

export const NativeTooltipSuppressor = () => {
  useEffect(() => {
    suppressNativeTooltipsIn(document.body);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (
          mutation.type === "attributes" &&
          mutation.attributeName === NATIVE_TITLE_ATTRIBUTE &&
          mutation.target instanceof Element
        ) {
          suppressNativeTooltip(mutation.target);
          continue;
        }

        if (mutation.type !== "childList") {
          continue;
        }

        mutation.addedNodes.forEach((node) => {
          if (node instanceof Element) {
            suppressNativeTooltipsIn(node);
          }
        });
      }
    });

    observer.observe(document.body, {
      attributeFilter: [NATIVE_TITLE_ATTRIBUTE],
      attributes: true,
      childList: true,
      subtree: true
    });

    return () => {
      observer.disconnect();
    };
  }, []);

  return null;
};
