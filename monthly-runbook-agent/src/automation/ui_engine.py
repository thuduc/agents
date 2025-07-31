"""UI automation engine using Playwright."""

import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..config.models import UIAutomationConfig

logger = logging.getLogger(__name__)


@dataclass
class UIStep:
    """Represents a single UI automation step."""
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    timeout: Optional[int] = None
    expected_text: Optional[str] = None
    screenshot: bool = False
    description: Optional[str] = None


@dataclass
class UIAutomationResult:
    """Result of UI automation execution."""
    success: bool
    message: str
    details: Dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    # Execution metrics
    total_steps: int = 0
    completed_steps: int = 0
    failed_step: Optional[int] = None
    
    # Screenshots and artifacts
    screenshots: List[str] = None
    page_source: Optional[str] = None
    console_logs: List[str] = None
    
    def __post_init__(self):
        if self.screenshots is None:
            self.screenshots = []
        if self.console_logs is None:
            self.console_logs = []
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class UIAutomationEngine:
    """Playwright-based UI automation engine."""
    
    def __init__(self, screenshots_dir: Optional[Union[str, Path]] = None):
        self.screenshots_dir = Path(screenshots_dir or "./screenshots")
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Browser instances (for reuse)
        self._playwright = None
        self._browsers: Dict[str, Browser] = {}
        
    async def initialize(self):
        """Initialize Playwright and browsers."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            logger.info("Playwright initialized")
    
    async def cleanup(self):
        """Clean up browsers and Playwright."""
        for browser_name, browser in self._browsers.items():
            try:
                await browser.close()
                logger.info(f"Closed {browser_name} browser")
            except Exception as e:
                logger.error(f"Error closing {browser_name} browser: {e}")
        
        self._browsers.clear()
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            logger.info("Playwright stopped")
    
    async def execute_automation(
        self,
        config: UIAutomationConfig,
        variables: Optional[Dict[str, str]] = None
    ) -> UIAutomationResult:
        """
        Execute UI automation based on configuration.
        
        Args:
            config: UI automation configuration
            variables: Variable substitutions (e.g., credentials)
            
        Returns:
            UIAutomationResult with execution details
        """
        started_at = datetime.utcnow()
        variables = variables or {}
        
        try:
            await self.initialize()
            
            # Parse steps from config
            steps = self._parse_steps(config.steps or [])
            
            result = UIAutomationResult(
                success=False,
                message="Starting UI automation",
                details={'config': config.__dict__},
                started_at=started_at,
                total_steps=len(steps)
            )
            
            async with self._get_browser_context(config) as (page, context):
                # Set up logging
                await self._setup_page_logging(page, result)
                
                # Navigate to initial URL
                if config.url:
                    await page.goto(self._substitute_variables(config.url, variables))
                    logger.info(f"Navigated to: {config.url}")
                
                # Execute steps
                for i, step in enumerate(steps):
                    try:
                        await self._execute_step(page, step, variables, result, i)
                        result.completed_steps += 1
                        logger.info(f"Completed step {i+1}: {step.action}")
                        
                    except Exception as e:
                        result.failed_step = i
                        error_msg = f"Step {i+1} failed: {str(e)}"
                        logger.error(error_msg)
                        
                        # Take failure screenshot
                        if config.screenshot_on_failure:
                            screenshot_path = await self._take_screenshot(
                                page, f"failure_step_{i+1}", result
                            )
                            logger.info(f"Failure screenshot: {screenshot_path}")
                        
                        result.message = error_msg
                        result.details['error'] = str(e)
                        result.details['failed_step'] = i + 1
                        result.completed_at = datetime.utcnow()
                        return result
                
                # Success - take final screenshot
                final_screenshot = await self._take_screenshot(page, "final", result)
                logger.info(f"Final screenshot: {final_screenshot}")
                
                # Capture page source
                result.page_source = await page.content()
                
                result.success = True
                result.message = f"UI automation completed successfully ({len(steps)} steps)"
                result.completed_at = datetime.utcnow()
                
                return result
                
        except Exception as e:
            logger.exception("UI automation failed with unexpected error")
            result.success = False
            result.message = f"UI automation failed: {str(e)}"
            result.details['error'] = str(e)
            result.completed_at = datetime.utcnow()
            return result
    
    @asynccontextmanager
    async def _get_browser_context(self, config: UIAutomationConfig):
        """Get browser context for automation."""
        browser_type = config.browser.lower()
        
        # Get or create browser
        if browser_type not in self._browsers:
            if browser_type == 'chromium':
                browser = await self._playwright.chromium.launch(
                    headless=config.headless,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
            elif browser_type == 'firefox':
                browser = await self._playwright.firefox.launch(headless=config.headless)
            elif browser_type == 'webkit':
                browser = await self._playwright.webkit.launch(headless=config.headless)
            else:
                raise ValueError(f"Unsupported browser: {browser_type}")
            
            self._browsers[browser_type] = browser
            logger.info(f"Launched {browser_type} browser")
        
        browser = self._browsers[browser_type]
        
        # Create context
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        # Create page
        page = await context.new_page()
        page.set_default_timeout(config.timeout_seconds * 1000)
        
        try:
            yield page, context
        finally:
            await context.close()
    
    async def _setup_page_logging(self, page: Page, result: UIAutomationResult):
        """Set up page event logging."""
        page.on("console", lambda msg: result.console_logs.append(
            f"[{msg.type}] {msg.text}"
        ))
        
        page.on("pageerror", lambda error: result.console_logs.append(
            f"[ERROR] {error}"
        ))
    
    def _parse_steps(self, steps_config: List[Dict[str, Any]]) -> List[UIStep]:
        """Parse steps configuration into UIStep objects."""
        steps = []
        
        for step_config in steps_config:
            step = UIStep(
                action=step_config['action'],
                selector=step_config.get('selector'),
                value=step_config.get('value'),
                url=step_config.get('url'),
                timeout=step_config.get('timeout'),
                expected_text=step_config.get('expected_text'),
                screenshot=step_config.get('screenshot', False),
                description=step_config.get('description')
            )
            steps.append(step)
        
        return steps
    
    async def _execute_step(
        self,
        page: Page,
        step: UIStep,
        variables: Dict[str, str],
        result: UIAutomationResult,
        step_index: int
    ):
        """Execute a single UI automation step."""
        action = step.action.lower()
        timeout = (step.timeout or 30) * 1000  # Convert to milliseconds
        
        # Substitute variables in step parameters
        selector = self._substitute_variables(step.selector, variables) if step.selector else None
        value = self._substitute_variables(step.value, variables) if step.value else None
        url = self._substitute_variables(step.url, variables) if step.url else None
        
        if action == 'navigate':
            if not url:
                raise ValueError("navigate action requires url parameter")
            await page.goto(url, timeout=timeout)
            
        elif action == 'click':
            if not selector:
                raise ValueError("click action requires selector parameter")
            await page.click(selector, timeout=timeout)
            
        elif action == 'fill':
            if not selector or value is None:
                raise ValueError("fill action requires selector and value parameters")
            await page.fill(selector, value, timeout=timeout)
            
        elif action == 'type':
            if not selector or value is None:
                raise ValueError("type action requires selector and value parameters")
            await page.type(selector, value, timeout=timeout, delay=100)
            
        elif action == 'select':
            if not selector or value is None:
                raise ValueError("select action requires selector and value parameters")
            await page.select_option(selector, value, timeout=timeout)
            
        elif action == 'wait':
            if selector:
                # Wait for element
                await page.wait_for_selector(selector, timeout=timeout)
            elif step.timeout:
                # Wait for specified time
                await asyncio.sleep(step.timeout)
            else:
                raise ValueError("wait action requires selector or timeout parameter")
            
        elif action == 'wait_for_text':
            if not selector or not step.expected_text:
                raise ValueError("wait_for_text action requires selector and expected_text parameters")
            expected_text = self._substitute_variables(step.expected_text, variables)
            await page.wait_for_function(
                f"document.querySelector('{selector}').textContent.includes('{expected_text}')",
                timeout=timeout
            )
            
        elif action == 'scroll':
            if selector:
                # Scroll to element
                await page.locator(selector).scroll_into_view_if_needed()
            else:
                # Scroll page
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
        elif action == 'screenshot':
            screenshot_name = f"step_{step_index + 1}"
            if step.description:
                screenshot_name += f"_{step.description.replace(' ', '_')}"
            await self._take_screenshot(page, screenshot_name, result)
            
        elif action == 'assert_text':
            if not selector or not step.expected_text:
                raise ValueError("assert_text action requires selector and expected_text parameters")
            expected_text = self._substitute_variables(step.expected_text, variables)
            element = page.locator(selector)
            actual_text = await element.text_content(timeout=timeout)
            if expected_text not in actual_text:
                raise AssertionError(f"Expected text '{expected_text}' not found. Actual: '{actual_text}'")
            
        elif action == 'assert_visible':
            if not selector:
                raise ValueError("assert_visible action requires selector parameter")
            await page.wait_for_selector(selector, state='visible', timeout=timeout)
            
        elif action == 'press_key':
            if not value:
                raise ValueError("press_key action requires value parameter (key name)")
            if selector:
                await page.locator(selector).press(value)
            else:
                await page.keyboard.press(value)
            
        elif action == 'hover':
            if not selector:
                raise ValueError("hover action requires selector parameter")
            await page.hover(selector, timeout=timeout)
            
        elif action == 'double_click':
            if not selector:
                raise ValueError("double_click action requires selector parameter")
            await page.dblclick(selector, timeout=timeout)
            
        elif action == 'drag_and_drop':
            if not selector or not step.value:
                raise ValueError("drag_and_drop action requires selector (source) and value (target) parameters")
            target_selector = self._substitute_variables(step.value, variables)
            await page.drag_and_drop(selector, target_selector, timeout=timeout)
            
        elif action == 'upload_file':
            if not selector or not value:
                raise ValueError("upload_file action requires selector and value (file path) parameters")
            file_path = Path(value)
            if not file_path.exists():
                raise FileNotFoundError(f"Upload file not found: {file_path}")
            await page.set_input_files(selector, str(file_path))
            
        elif action == 'switch_frame':
            if selector:
                frame = page.frame_locator(selector)
                # Note: Frame switching in Playwright is different from Selenium
                # You work with frame locators directly
                pass
            else:
                raise ValueError("switch_frame action requires selector parameter")
            
        elif action == 'execute_js':
            if not value:
                raise ValueError("execute_js action requires value parameter (JavaScript code)")
            js_code = self._substitute_variables(value, variables)
            await page.evaluate(js_code)
            
        else:
            raise ValueError(f"Unknown action: {action}")
        
        # Take screenshot if requested
        if step.screenshot:
            screenshot_name = f"step_{step_index + 1}_{action}"
            await self._take_screenshot(page, screenshot_name, result)
    
    async def _take_screenshot(
        self,
        page: Page,
        name: str,
        result: UIAutomationResult
    ) -> str:
        """Take a screenshot and save it."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{name}.png"
        filepath = self.screenshots_dir / filename
        
        try:
            await page.screenshot(path=str(filepath), full_page=True)
            result.screenshots.append(str(filepath))
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to take screenshot {name}: {e}")
            return ""
    
    def _substitute_variables(
        self,
        text: Optional[str],
        variables: Dict[str, str]
    ) -> Optional[str]:
        """Substitute variables in text using ${VAR} syntax."""
        if not text or not variables:
            return text
        
        result = text
        for key, value in variables.items():
            placeholder = f"${{{key}}}"
            result = result.replace(placeholder, value)
        
        return result
    
    async def validate_configuration(self, config: UIAutomationConfig) -> List[str]:
        """Validate UI automation configuration."""
        errors = []
        
        if not config.url:
            errors.append("URL is required for UI automation")
        
        if config.browser not in ['chromium', 'firefox', 'webkit']:
            errors.append(f"Unsupported browser: {config.browser}")
        
        if config.timeout_seconds <= 0:
            errors.append("Timeout must be positive")
        
        # Validate steps
        if config.steps:
            for i, step_config in enumerate(config.steps):
                step_errors = self._validate_step(step_config, i)
                errors.extend(step_errors)
        
        return errors
    
    def _validate_step(self, step_config: Dict[str, Any], index: int) -> List[str]:
        """Validate a single step configuration."""
        errors = []
        prefix = f"Step {index + 1}"
        
        if 'action' not in step_config:
            errors.append(f"{prefix}: action is required")
            return errors
        
        action = step_config['action'].lower()
        
        # Actions that require selector
        if action in ['click', 'fill', 'type', 'select', 'assert_text', 'assert_visible', 'hover', 'double_click']:
            if not step_config.get('selector'):
                errors.append(f"{prefix}: {action} action requires selector")
        
        # Actions that require value
        if action in ['fill', 'type', 'select', 'press_key', 'execute_js']:
            if 'value' not in step_config:
                errors.append(f"{prefix}: {action} action requires value")
        
        # Actions that require URL
        if action == 'navigate':
            if not step_config.get('url'):
                errors.append(f"{prefix}: navigate action requires url")
        
        # Actions that require expected_text
        if action in ['wait_for_text', 'assert_text']:
            if not step_config.get('expected_text'):
                errors.append(f"{prefix}: {action} action requires expected_text")
        
        return errors