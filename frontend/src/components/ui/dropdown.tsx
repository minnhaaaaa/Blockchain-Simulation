import { Children, isValidElement, type ReactNode, type SelectHTMLAttributes } from "react";
import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";

// The supplied monochrome dropdown, with Radix keyboard, focus and portal handling.
// Keep native option children so every field shares the same accessible control.
type Props = Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "multiple" | "size"> & {
  onChange?: (event: { target: { value: string } }) => void;
};
const EMPTY = "__certa_empty_selection__";
export function Dropdown({ children, value, defaultValue, onChange, disabled, required, name, id, className, ...props }: Props) {
  const options = Children.toArray(children).filter(isValidElement<{ value?: string; disabled?: boolean; children: ReactNode }>);
  const encode = (v: unknown) => String(v ?? "") || EMPTY;
  return <Select.Root {...(value === undefined ? {} : { value: encode(value) })} {...(defaultValue === undefined ? {} : { defaultValue: encode(defaultValue) })}
    onValueChange={next => onChange?.({ target: { value: next === EMPTY ? "" : next } })} disabled={Boolean(disabled)} required={Boolean(required)} {...(name ? { name } : {})}>
    <Select.Trigger id={id} className={`certa-select ${className ?? ""}`} aria-label={props["aria-label"]} aria-describedby={props["aria-describedby"]} aria-required={required}>
      <Select.Value/><Select.Icon><ChevronDown size={16}/></Select.Icon>
    </Select.Trigger>
    <Select.Portal><Select.Content className="certa-select-menu" position="popper" sideOffset={8} collisionPadding={16}>
      <Select.ScrollUpButton className="select-scroll"><ChevronUp size={15}/></Select.ScrollUpButton>
      <Select.Viewport>{options.map((option, index) => <Select.Item key={encode(option.props.value ?? option.props.children)}
        value={encode(option.props.value ?? option.props.children)} disabled={Boolean(option.props.disabled)} className="certa-select-option" style={{ animationDelay: `${Math.min(index, 6) * 25}ms` }}>
        <Select.ItemText>{option.props.children}</Select.ItemText><Select.ItemIndicator><Check size={16}/></Select.ItemIndicator>
      </Select.Item>)}</Select.Viewport>
      <Select.ScrollDownButton className="select-scroll"><ChevronDown size={15}/></Select.ScrollDownButton>
    </Select.Content></Select.Portal>
  </Select.Root>;
}
