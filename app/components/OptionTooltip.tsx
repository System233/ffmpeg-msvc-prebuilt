import { Tooltip } from "@base-ui/react/tooltip";
import { useId, useState, type ReactElement } from "react";

export function OptionTooltip({
  text,
  children,
  disabled = false,
}: {
  text?: string;
  children: ReactElement;
  disabled?: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  if (!text) return children;
  return (
    <Tooltip.Root
      disabled={disabled}
      open={open && !disabled}
      onOpenChange={setOpen}
    >
      <Tooltip.Trigger
        render={children}
        aria-describedby={open && !disabled ? id : undefined}
      />
      <Tooltip.Portal>
        <Tooltip.Positioner
          className="option-tooltip-positioner"
          side="top"
          sideOffset={8}
          collisionPadding={12}
          collisionAvoidance={{
            side: "flip",
            align: "shift",
            fallbackAxisSide: "none",
          }}
        >
          <Tooltip.Popup id={id} role="tooltip" className="option-tooltip">
            {text}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
