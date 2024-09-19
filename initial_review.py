import json
import logging
from typing import Dict, Any, List
import anthropic
from anthropic.types import Message

logger = logging.getLogger(__name__)

class InitialReview:
    def __init__(self, client: anthropic.Anthropic, config: Dict[str, Any]):
        """
        Initialize the InitialReview instance.

        Args:
            client (anthropic.Anthropic): The Anthropic client for making API calls.
            config (Dict[str, Any]): Configuration dictionary for the Anthropic API.
        """
        self.client = client
        self.config = config
        logger.info("InitialReview initialized with config: %s", json.dumps(config))

    async def assess_simplicity_clarity(self, user_input: str, ai_response: str) -> Dict[str, Any]:
        """
        Assess the simplicity and clarity of the meaning and context in both user input and AI response.

        Args:
            user_input (str): The user's input to be assessed.
            ai_response (str): The AI's response to be assessed.

        Returns:
            Dict[str, Any]: Assessment results including scores and whether to proceed with WiseCounsel.
        """
        logger.info("Starting initial simplicity and clarity assessment of meaning and context")

        system_message = """
        You are an expert in assessing the simplicity and clarity of meaning and context in communication. Your task is to evaluate both a user's input and an AI's response, focusing on the underlying meaning and contextual relevance rather than just the surface-level text. Rate them on a scale from 1 to 100, where:

        1 is extremely complex, unclear in meaning, or lacking contextual relevance.
        100 is very simple, clear in meaning, and highly relevant to the context.

        Consider factors such as:
        - Coherence of ideas
        - Relevance to the conversation context
        - Ease of understanding the intended meaning
        - Absence of ambiguity or confusion in the message

        Please provide your assessment in the following format:

        <assessment>
        <user_score>Score for user input</user_score>
        <user_explanation>Brief explanation for user input score, focusing on meaning and context</user_explanation>
        <ai_score>Score for AI response</ai_score>
        <ai_explanation>Brief explanation for AI response score, focusing on meaning and context</ai_explanation>
        </assessment>

        Ensure that your scores are integers between 1 and 100.
        """

        user_message = f"""
        Please assess the simplicity and clarity of the following user input and AI response:

        User Input:
        {user_input}

        AI Response:
        {ai_response}
        """

        try:
            assessment_response = await self._get_assessment(system_message, user_message)
            logger.info("Received initial assessment response")

            assessment_text = assessment_response.content[0].text if assessment_response.content else ""
            logger.info("Extracted initial assessment text (length: %d): %s", len(assessment_text), assessment_text)

            user_score, user_explanation, ai_score, ai_explanation = self._parse_assessment(assessment_text)

            proceed_with_wise_counsel = user_score < 50 and ai_score < 60

            result = {
                "user_score": user_score,
                "user_explanation": user_explanation,
                "ai_score": ai_score,
                "ai_explanation": ai_explanation,
                "proceed_with_wise_counsel": proceed_with_wise_counsel
            }

            logger.info("Initial assessment completed. Result: %s", json.dumps(result))
            return result

        except Exception as e:
            logger.error("Error in initial assessment process: %s", str(e))
            return {
                "user_score": 0,
                "user_explanation": "Error occurred during initial assessment",
                "ai_score": 0,
                "ai_explanation": "Error occurred during initial assessment",
                "proceed_with_wise_counsel": False
            }

    async def _get_assessment(self, system_message: str, user_message: str) -> Message:
        """
        Get an assessment from the AI.

        Args:
            system_message (str): The system message containing assessment instructions.
            user_message (str): The user message containing the text to be assessed.

        Returns:
            Message: The AI's assessment response.

        Raises:
            Exception: If there's an error in the API call.
        """
        logger.info("Getting initial assessment response")
        messages = [{"role": "user", "content": user_message}]
        logger.info("Messages for API call: %s", json.dumps(messages))
        return await self._make_api_call(system_message, messages)

    async def _make_api_call(self, system: str, messages: List[Dict[str, str]]) -> Message:
        """
        Make an API call to the Anthropic client.

        Args:
            system (str): The system message.
            messages (List[Dict[str, str]]): The list of messages for the conversation.

        Returns:
            Message: The response from the Anthropic API.

        Raises:
            Exception: If there's an error in the API call.
        """
        logger.info("Making API call to Anthropic for initial review")
        try:
            response = self.client.messages.create(
                model=self.config['model_name'],
                max_tokens=1000,  # Adjusted for shorter responses
                system=system,
                messages=messages,
                extra_headers=self.config.get('anthropic_headers', {})
            )
            logger.info("Initial review API call successful. Response: %s", json.dumps(response.model_dump()))
            return response
        except Exception as e:
            logger.error("Error in initial review API call: %s", str(e))
            raise

    def _parse_assessment(self, assessment_text: str) -> tuple:
        """
        Parse the assessment text to extract scores and explanations.

        Args:
            assessment_text (str): The text containing the assessment.

        Returns:
            tuple: (user_score, user_explanation, ai_score, ai_explanation)
        """
        import re

        user_score_match = re.search(r'<user_score>(\d+)</user_score>', assessment_text)
        user_explanation_match = re.search(r'<user_explanation>(.*?)</user_explanation>', assessment_text, re.DOTALL)
        ai_score_match = re.search(r'<ai_score>(\d+)</ai_score>', assessment_text)
        ai_explanation_match = re.search(r'<ai_explanation>(.*?)</ai_explanation>', assessment_text, re.DOTALL)

        user_score = int(user_score_match.group(1)) if user_score_match else 0
        user_explanation = user_explanation_match.group(1).strip() if user_explanation_match else ""
        ai_score = int(ai_score_match.group(1)) if ai_score_match else 0
        ai_explanation = ai_explanation_match.group(1).strip() if ai_explanation_match else ""

        return user_score, user_explanation, ai_score, ai_explanation

logger.info("initial_review.py module loaded")
