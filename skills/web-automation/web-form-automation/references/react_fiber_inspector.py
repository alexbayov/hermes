#!/usr/bin/env python3
"""
React fiber inspector for Playwright — use when standard page.fill()
does not trigger form submission on React Hook Form / Next.js pages.
"""
from playwright.sync_api import sync_playwright

def inspect_react_fiber(page, selector):
    """Return component tree from a DOM element's React fiber."""
    return page.evaluate("""
        (selector) => {
            const el = document.querySelector(selector);
            if (!el) return {error: 'element not found'};
            
            const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
            if (!fiberKey) return {error: 'no react fiber'};
            
            const fiber = el[fiberKey];
            let current = fiber;
            let depth = 0;
            const tree = [];
            
            while (current && depth < 20) {
                const props = current.memoizedProps || {};
                const name = current.elementType?.name || current.elementType?.displayName || String(current.elementType);
                tree.push({
                    name: name.substring(0, 50),
                    hasAction: !!props.action,
                    hasOnSubmit: !!props.onSubmit,
                    hasOnClick: !!props.onClick,
                    hasDisabled: !!props.disabled,
                    props: Object.keys(props).filter(k => k !== 'children')
                });
                current = current.return;
                depth++;
            }
            return {fiberKey, tree};
        }
    """, selector)


def trigger_react_click(page, selector):
    """Trigger onClick via React props when DOM click fails."""
    return page.evaluate("""
        (selector) => {
            const el = document.querySelector(selector);
            if (!el) return 'no element';
            
            const propsKey = Object.keys(el).find(k => k.startsWith('__reactProps$'));
            const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
            
            if (propsKey && el[propsKey].onClick) {
                el[propsKey].onClick({preventDefault: ()=>{}, stopPropagation: ()=>{}});
                return 'props.onClick triggered';
            }
            
            if (fiberKey) {
                let current = el[fiberKey];
                while (current) {
                    if (current.memoizedProps?.onClick) {
                        current.memoizedProps.onClick({preventDefault: ()=>{}, stopPropagation: ()=>{}});
                        return 'fiber.onClick triggered';
                    }
                    current = current.return;
                }
            }
            
            return 'no onClick found';
        }
    """, selector)


def trigger_react_submit(page):
    """Trigger form onSubmit via React fiber."""
    return page.evaluate("""
        () => {
            const form = document.querySelector('form');
            if (!form) return 'no form';
            
            const fiberKey = Object.keys(form).find(k => k.startsWith('__reactFiber$'));
            if (!fiberKey) {
                // Fallback: native submit
                form.dispatchEvent(new SubmitEvent('submit', {bubbles: true}));
                return 'native submit dispatched';
            }
            
            let current = form[fiberKey];
            while (current) {
                if (current.memoizedProps?.onSubmit) {
                    current.memoizedProps.onSubmit({preventDefault: ()=>{}, stopPropagation: ()=>{}});
                    return 'fiber.onSubmit triggered';
                }
                current = current.return;
            }
            
            return 'no onSubmit found';
        }
    """)


if __name__ == '__main__':
    # Example usage
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto('https://example.com/form')
        
        print(inspect_react_fiber(page, 'button[type="submit"]'))
        print(trigger_react_click(page, 'button[type="submit"]'))
        
        browser.close()
