import { createPopper, type Placement } from "@popperjs/core";
import { onMounted, onUnmounted, type Ref, ref, watch } from "vue";

export type Trigger = "click" | "hover" | "manual";

export type EventOptions = {
    onShow: () => void;
    onHide: () => void;
};

const defaultTrigger: Trigger = "hover";

export function usePopperjs(
    reference: Ref<HTMLElement>,
    popper: Ref<HTMLElement>,
    options: {
        placement: Placement | undefined;
        trigger: Trigger | undefined;
        delayOnMouseover: number | undefined;
        delayOnMouseout: number | undefined;
        onShow: () => void;
        onHide: () => void;
    }
) {
    const instance = ref<ReturnType<typeof createPopper>>();

    onMounted(() => {
        // create instance
        instance.value = createPopper(reference.value, popper.value!, {
            placement: options?.placement ?? "bottom",
            strategy: "absolute",
        });

        // attach event handlers
        switch (options?.trigger ?? defaultTrigger) {
            case "click": {
                reference.value.addEventListener("click", doOpen);
                document.addEventListener("click", doCloseForDocument);
                break;
            }

            case "hover": {
                reference.value.addEventListener("mousedown", doMouseout);
                reference.value.addEventListener("mouseout", doMouseout);
                reference.value.addEventListener("mouseover", doMouseover);
                break;
            }

            case "manual": {
                break;
            }

            default: {
                throw TypeError();
            }
        }
    });

    onUnmounted(() => {
        // destroy instance
        instance.value?.destroy();
        instance.value = undefined;

        // remove event handlers
        document.removeEventListener("click", doCloseForDocument, false);
        if (reference.value) {
            reference.value.removeEventListener("click", doOpen, false);
            reference.value.removeEventListener("mousedown", doMouseout, false);
            reference.value.removeEventListener("mouseover", doMouseover, false);
            reference.value.removeEventListener("mouseout", doMouseout, false);
        }
    });

    const visible = ref(false);
    const doOpen = () => (visible.value = true);
    const doClose = () => (visible.value = false);
    const timer = ref<any>();

    const doMouseover = () => {
        if (options?.delayOnMouseover === 0) {
            doOpen();
        } else {
            clearTimeout(timer.value);
            timer.value = setTimeout(() => {
                doOpen();
            }, options?.delayOnMouseover ?? 100);
        }
    };

    const doMouseout = () => {
        if (options?.delayOnMouseout === 0) {
            doClose();
        } else {
            clearTimeout(timer.value);
            timer.value = setTimeout(() => {
                doClose();
            }, options?.delayOnMouseout ?? 100);
        }
    };

    const doCloseForDocument = (e: Event) => {
        if (reference.value?.contains(e.target as Element)) {
            return;
        }
        if (popper.value?.contains(e.target as Element)) {
            return;
        }
        doClose();
    };

    watch(
        () => [instance.value, visible.value],
        () => {
            if (instance.value) {
                if (visible.value) {
                    popper.value?.classList.remove("vue-use-popperjs-none");
                    options?.onShow?.();
                    instance.value?.update();
                } else {
                    popper.value?.classList.add("vue-use-popperjs-none");
                    options?.onHide?.();
                }
            }
        }
    );

    return {
        instance,
        visible,
    };
}
