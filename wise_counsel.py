# wise_counsel.py

import logging
import textwrap
import re
import json
from typing import Dict, Union, Any, List
import anthropic
from anthropic.types import Message

logger = logging.getLogger(__name__)

def wrap_text_for_logging(content: Any, width: int = 100, max_length: int = 10000) -> str:
    """
    Wrap and format content for better readability in logs.
    
    Args:
        content (Any): The content to wrap. Can be a string, dict, list, or any other type.
        width (int): The maximum width of each line. Default is 100.
        max_length (int): The maximum total length of the output. Default is 10000.
    
    Returns:
        str: The wrapped and formatted text.
    """
    def format_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        else:
            return str(value)

    separator = "=" * width
    header = "-" * width

    if isinstance(content, dict):
        formatted_content = "Dictionary Content:\n" + header + "\n"
        for key, value in content.items():
            formatted_value = format_value(value)
            formatted_content += f"{key}:\n{textwrap.indent(formatted_value, '  ')}\n"
    elif isinstance(content, list):
        formatted_content = "List Content:\n" + header + "\n"
        for item in content:
            formatted_item = format_value(item)
            formatted_content += f"- {formatted_item}\n"
    else:
        formatted_content = "Content:\n" + header + "\n" + str(content)

    wrapped_lines = []
    for line in formatted_content.split('\n'):
        wrapped_lines.extend(textwrap.wrap(line, width=width, break_long_words=False, replace_whitespace=False))

    wrapped_text = '\n'.join(wrapped_lines)

    if len(wrapped_text) > max_length:
        wrapped_text = wrapped_text[:max_length] + "\n... [truncated]"

    return f"\n{separator}\n{wrapped_text}\n{separator}\n"

class WiseCounsel:
    def __init__(self, client: anthropic.Anthropic, config: Dict[str, Any]):
        """
        Initialize the WiseCounsel instance.

        Args:
            client (anthropic.Anthropic): The Anthropic client for making API calls.
            config (Dict[str, Any]): Configuration dictionary for the Anthropic API.
        """
        self.client = client
        self.config = config
        logger.info("WiseCounsel initialized with config:\n%s", wrap_text_for_logging(str(config)))

    async def review_response(self, response: Message, context: str, base_prompt: str) -> Dict[str, Any]:
        """
        Review the response from Claude by making a separate API call, with a highly critical approach.

        Args:
            response (Message): The original response from Claude to be reviewed.
            context (str): The conversation context.
            base_prompt (str): The base prompt used in the conversation.

        Returns:
            Dict[str, Any]: The review result, containing approval status and any feedback.
        """
        logger.info("Starting review_response method")
        
        # Extract the text content from the response
        response_text = "".join(content.text for content in response.content if content.type == 'text')
        logger.info("Extracted response text (length: %d):\n%s", len(response_text), wrap_text_for_logging(response_text))

        # Prepare the system message with strict review instructions
        system_message = f"""
        You are an extremely critical AI consultant tasked with meticulously reviewing AI-generated responses. Your job is to scrutinize the following response with the highest standards, considering these criteria:

        1. Adherence to guidelines and context (Score 0-10)
        2. Accuracy and correctness of information (Score 0-10)
        3. Clarity and coherence of the response (Score 0-10)
        4. Appropriateness of tone and style (Score 0-10)
        5. Consistency with the base prompt (Score 0-10)
        6. Depth and insightfulness of the response (Score 0-10)
        7. Creativity and innovative thinking (Score 0-10)
        8. Practical applicability of any suggestions or solutions (Score 0-10)
        9. Anticipation of potential issues or edge cases (Score 0-10)
        10. Overall impression and effectiveness (Score 0-10)

        The context of the conversation is:
        <context>
        {context}
        </context>

        The base prompt used in the conversation is:
        <base_prompt>
        {base_prompt}
        </base_prompt>

        Provide your assessment in the following format:
        1. Detailed evaluation of each criterion (2-3 sentences each, including the score)
        2. In-depth comparison with the base prompt (3-4 sentences)
        3. Comprehensive feedback and specific suggestions for improvement (be extremely thorough)
        4. List of at least 5 ways the response could be enhanced or optimized
        5. Identification of any missed opportunities or unexplored angles in the response
        6. Final verdict and total score: This step is CRITICAL and MUST be followed EXACTLY as described:

           a. Calculate the total score out of 100.

           b. You MUST use the following format to report the final verdict:

              <final_verdict>
              <total_score>total score: [YOUR CALCULATED SCORE]</total_score>
              <approval_status>[APPROVAL DECISION]</approval_status>
              [EXPLANATION IF NOT APPROVED]
              </final_verdict>

           c. Replace [YOUR CALCULATED SCORE] with the actual numeric score you calculated.

           d. Replace [APPROVAL DECISION] with either "APPROVED" or "NOT APPROVED" based on these criteria:
              - If the total score is 90 or above AND no individual criterion scores below 8, use "APPROVED"
              - Otherwise, use "NOT APPROVED"

           e. If the decision is "NOT APPROVED", provide a detailed explanation of why it falls short 
              immediately after the </approval_status> tag but still within the <final_verdict> tags.

           Example of a complete final verdict:

           <final_verdict>
           <total_score>total score: 95</total_score>
           <approval_status>APPROVED</approval_status>
           </final_verdict>

           OR

           <final_verdict>
           <total_score>total score: 85</total_score>
           <approval_status>NOT APPROVED</approval_status>
           This response falls short of approval because the total score is below 90. 
           Additionally, the response lacks depth in addressing [specific issue], and 
           the proposed solution for [particular problem] is not sufficiently detailed.
           </final_verdict>

        IMPORTANT: Failure to follow this format precisely will be considered a critical error in your review. 
        All tags (<final_verdict>, <total_score>, and <approval_status>) are mandatory and will be used 
        for automated processing of your review. Ensure that the tags are correctly opened and closed, 
        and that the content within each tag is accurate and follows the specified format.

        Be extremely picky and demanding in your review. Look for any possible flaws, inconsistencies, or areas for improvement, no matter how small. The goal is to ensure only the highest quality responses are approved. Do not hesitate to be critical - it's better to be too strict than too lenient.
        """

        logger.info("Prepared system message (length: %d):\n%s", len(system_message), wrap_text_for_logging(system_message))

        user_message = f"Please conduct a rigorous and highly critical review of this AI response:\n\n<ai_response>{response_text}</ai_response>\n\nand compare it meticulously against the provided Base Prompt and Context."
        logger.info("Prepared user message (length: %d):\n%s", len(user_message), wrap_text_for_logging(user_message))

        try:
            review_response = await self._get_review_response(system_message, user_message)
            logger.info("Received review response")

            review_text = review_response.content[0].text if review_response.content else ""
            logger.info("Extracted review text (length: %d):\n%s", len(review_text), wrap_text_for_logging(review_text))

            # Parse the review text to determine approval and extract feedback
            approval_status_match = re.search(r'<approval_status>(.*?)</approval_status>', review_text, re.IGNORECASE | re.DOTALL)
            if approval_status_match:
                approval_status = approval_status_match.group(1).strip()
                approved = approval_status.upper() == "APPROVED"
                logger.info(f"Extracted approval status: {approval_status}")
            else:
                approved = False
                logger.warning("Could not find approval status in the expected format")

            feedback_match = re.search(r'<approval_status>.*?</approval_status>\s*(.*?)\s*</final_verdict>', review_text, re.IGNORECASE | re.DOTALL)
            if feedback_match:
                feedback = feedback_match.group(1).strip()
            else:
                feedback = ""
                logger.warning("Could not extract feedback from the review")

            logger.info(f"Extracted feedback: {feedback[:100]}..." if len(feedback) > 100 else feedback)

            # Extract the total score
            total_score = 0
            total_score_match = re.search(r'<total_score>total score:\s*(\d+)</total_score>', review_text)
            if total_score_match:
                try:
                    total_score = int(total_score_match.group(1))
                except ValueError:
                    logger.warning("Could not parse total score from: %s", total_score_match.group(0))
            else:
                logger.warning("Could not find total score in the expected format")

            result = {
                "approved": approved,
                "feedback": feedback,
                "full_review": review_text,
                "total_score": total_score
            }
            logger.info("Review completed. Result:\n%s", wrap_text_for_logging(str(result)))

            return result

        except Exception as e:
            logger.error("Error in review process: %s", str(e))
            return {
                "approved": False,
                "feedback": "An error occurred during the review process.",
                "full_review": str(e),
                "total_score": 0
            }

    async def _get_review_response(self, system_message: str, user_message: str) -> Message:
        """
        Get a response from the AI for reviewing purposes.

        Args:
            system_message (str): The system message containing review instructions.
            user_message (str): The user message containing the response to be reviewed.

        Returns:
            Message: The AI's review response.

        Raises:
            Exception: If there's an error in the API call.
        """
        logger.info("Getting review response")
        messages = [{"role": "user", "content": user_message}]
        logger.info("Messages for API call:\n%s", wrap_text_for_logging(str(messages)))
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
        logger.info("Making API call to Anthropic")
        try:
            response = self.client.messages.create(
                model=self.config['model_name'],
                max_tokens=self.config.get('max_tokens', 2000),  # Increased max_tokens for more detailed reviews
                system=system,
                messages=messages,
                extra_headers=self.config.get('anthropic_headers', {})
            )
            logger.info("API call successful. Response:\n%s", wrap_text_for_logging(str(response)))
            return response
        except Exception as e:
            logger.error("Error in API call: %s", str(e))
            raise

# You can add any additional utility functions or constants here if needed in the future

logger.info("wise_counsel.py module loaded")