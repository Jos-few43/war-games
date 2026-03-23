"""War Games Manager Crew - Autonomous season management with CrewAI."""

from crewai import Agent, Crew, Task, Process
from crewai.project import CrewBase, agent, crew, task
from crewai.tools import BashTool, FileReadTool, FileWriteTool, DirectoryReadTool

from wargames.crewai import TaskType


class WarGamesManagerCrew(CrewBase):
    """Autonomous war-games season management crew.

    This crew automates:
    - Full season execution and monitoring
    - CVE updates from NVD/ExploitDB
    - Strategy performance analysis
    - Bug bounty hunting (analyzing rounds for novel exploits)
    - Memory storage (Qdrant vector + shared memory)
    - CVE-style reporting for 0-day discoveries
    """

    @agent
    def season_manager(self) -> Agent:
        return Agent(
            role='Season Manager',
            goal='Efficiently orchestrate full war-games seasons from start to finish',
            backstory="""You are an expert at managing long-running AI simulations.
            You understand the seasonal nature of war-games and know how to
            monitor progress, handle pauses, and extract final results.
            You coordinate with other agents to ensure the season runs smoothly.""",
            verbose=True,
            allow_delegation=True,
            tools=[
                BashTool(),
                FileReadTool(),
                DirectoryReadTool(),
            ],
        )

    @agent
    def cve_crawler(self) -> Agent:
        return Agent(
            role='CVE Intelligence Analyst',
            goal='Keep attack scenarios updated with the latest vulnerabilities',
            backstory="""You are a security researcher specializing in vulnerability
            intelligence. You monitor NVD, ExploitDB, and GitHub Advisories to
            find the latest CVEs that can be used as attack scenarios in
            war-games. You ensure the red team has current, relevant exploits.""",
            verbose=True,
            allow_delegation=False,
            tools=[
                BashTool(),
                FileReadTool(),
                FileWriteTool(),
            ],
        )

    @agent
    def strategy_analyst(self) -> Agent:
        return Agent(
            role='Strategy Performance Analyst',
            goal='Analyze strategy effectiveness and recommend optimizations',
            backstory="""You are an AI strategy expert. You analyze the performance
            of attack and defense strategies extracted during war-games rounds.
            You identify patterns in successful strategies and recommend
            improvements to the teams. You use vector memory to find similar
            past strategies.""",
            verbose=True,
            allow_delegation=False,
            tools=[
                BashTool(),
                FileReadTool(),
            ],
        )

    @agent
    def bug_bounty_hunter(self) -> Agent:
        return Agent(
            role='Bug Bounty Hunter',
            goal='Find novel exploits and potential unreported vulnerabilities',
            backstory="""You are an experienced exploit developer turned bug bounty
            hunter. You analyze war-games round outputs to find novel attack
            patterns that could represent undisclosed vulnerabilities.
            Your output helps identify potential CVEs for responsible disclosure.
            You cross-reference findings with NVD to determine novelty.""",
            verbose=True,
            allow_delegation=False,
            tools=[
                BashTool(),
                FileReadTool(),
                FileWriteTool(),
            ],
        )

    @agent
    def memory_keeper(self) -> Agent:
        return Agent(
            role='Memory Keeper',
            goal='Store and retrieve cross-session knowledge using vector memory',
            backstory="""You are the institutional memory of war-games. You store
            round results, strategies, and discoveries in vector memory (Qdrant)
            and export important findings to shared memory for other AI systems
            to discover. You ensure continuity across seasons.""",
            verbose=True,
            allow_delegation=False,
            tools=[
                BashTool(),
                FileReadTool(),
                FileWriteTool(),
            ],
        )

    @task
    def run_season(self) -> Task:
        return Task(
            description="""Execute a complete war-games season.

            Steps:
            1. Check configuration is valid
            2. Start the season with 'wargames start --config config/default.toml'
            3. Monitor progress via 'wargames status' or database queries
            4. Handle any pauses/resumes as needed
            5. Extract final results and strategy performance
            6. Export results to JSON/markdown format

            Report on: total rounds, phase progression, ELO changes, top strategies.""",
            expected_output='Complete season report with round-by-round summary, ELO ratings, and strategy performance metrics',
            agent=self.season_manager(),
        )

    @task
    def update_cves(self) -> Task:
        return Task(
            description="""Update the CVE database with latest vulnerabilities.

            Steps:
            1. Run 'wargames crawl --sources nvd,exploitdb'
            2. Review new CVEs added
            3. Categorize by severity and relevance
            4. Report on new attack vectors available for next season""",
            expected_output='List of new CVEs added to rotation, categorized by severity and attack type',
            agent=self.cve_crawler(),
        )

    @task
    def analyze_strategies(self) -> Task:
        return Task(
            description="""Analyze strategy performance across completed rounds.

            Steps:
            1. Query database for strategy win rates by team and phase
            2. Identify top-performing strategies for each phase
            3. Find strategies with declining performance
            4. Recommend which strategies to emphasize in future rounds
            5. Identify any strategies that should be pruned""",
            expected_output='Strategy performance report with win rates, trends, and optimization recommendations',
            agent=self.strategy_analyst(),
        )

    @task
    def hunt_bugs(self) -> Task:
        return Task(
            description="""Analyze round outputs for potential unreported vulnerabilities.

            Steps:
            1. Query database for all bug reports from recent rounds
            2. Cross-reference with known CVEs in the system using NVD API
            3. Identify novel attack patterns not matching existing CVEs
            4. For each potential finding:
               - Document the attack vector
               - Assess severity and exploitability
               - Check if similar vulnerabilities exist in public databases
            5. Generate CVE-style report for potential 0-day findings
            6. Export reports to exploit-discoveries.md in vault""",
            expected_output='Bug bounty report with CVE-style reports for potential vulnerabilities categorized by severity and novelty',
            agent=self.bug_bounty_hunter(),
        )

    @task
    def store_memory(self) -> Task:
        return Task(
            description="""Store session knowledge in vector memory and shared memory.

            Steps:
            1. Query recent rounds from database
            2. Generate embeddings for rounds, strategies, and bug reports
            3. Store in Qdrant vector database (wargames_rounds, wargames_strategies, wargames_bugs)
            4. Export key insights to ~/Documents/OpenClaw-Vault/01-RESEARCH/WarGames/
            5. Write to shared-memory/core for cross-session discovery""",
            expected_output='Confirmation of memory storage with vector IDs and exported file paths',
            agent=self.memory_keeper(),
        )

    @task
    def retrieve_context(self) -> Task:
        return Task(
            description="""Retrieve relevant context from memory for current session.

            Steps:
            1. Query vector memory for similar past rounds
            2. Find relevant strategies by phase
            3. Get CVE intelligence for current domain
            4. Synthesize context for the current season""",
            expected_output='Context summary with relevant past rounds, strategies, and CVE intelligence',
            agent=self.memory_keeper(),
        )

    @task
    def run_full_season_with_analysis(self) -> Task:
        return Task(
            description="""Run a complete season with full memory and reporting pipeline.

            This is the main orchestration task that:
            1. Retrieves context from memory (retrieve_context)
            2. Runs the full season (run_season)
            3. Updates CVEs (update_cves)
            4. Analyzes strategies (analyze_strategies)
            5. Hunts for bugs with NVD cross-reference (hunt_bugs)
            6. Stores everything in memory (store_memory)

            Produces a comprehensive report with persistent memory.""",
            expected_output='Comprehensive season report with results, CVE updates, strategy analysis, vulnerabilities, and memory storage confirmation',
            agent=self.season_manager(),
            context=[
                self.retrieve_context(),
                self.run_season(),
                self.update_cves(),
                self.analyze_strategies(),
                self.hunt_bugs(),
                self.store_memory(),
            ],
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.season_manager(),
                self.cve_crawler(),
                self.strategy_analyst(),
                self.bug_bounty_hunter(),
                self.memory_keeper(),
            ],
            tasks=[
                self.run_season(),
                self.update_cves(),
                self.analyze_strategies(),
                self.hunt_bugs(),
                self.store_memory(),
                self.retrieve_context(),
                self.run_full_season_with_analysis(),
            ],
            process=Process.hierarchical,
            manager_llm='gemini-2-flash',
            verbose=True,
            memory=True,
            planning=True,
        )


def run_crew(task_name: str = 'run_full_season_with_analysis', inputs: dict | None = None):
    """Run the war-games manager crew.

    Args:
        task_name: Name of the task to run
        inputs: Input parameters for the task

    Example:
        >>> from wargames.crew.manager import run_crew
        >>> run_crew("run_season", {"rounds": 50})
    """
    crew = WarGamesManagerCrew()
    task_map = {
        'run_season': crew.run_season(),
        'update_cves': crew.update_cves(),
        'analyze_strategies': crew.analyze_strategies(),
        'hunt_bugs': crew.hunt_bugs(),
        'run_full_season_with_analysis': crew.run_full_season_with_analysis(),
    }

    if task_name not in task_map:
        raise ValueError(f'Unknown task: {task_name}. Available: {list(task_map.keys())}')

    result = crew.crew().kickoff(inputs=inputs or {})
    return result


if __name__ == '__main__':
    import sys

    task = sys.argv[1] if len(sys.argv) > 1 else 'run_full_season_with_analysis'
    result = run_crew(task)
    print(result.raw)
