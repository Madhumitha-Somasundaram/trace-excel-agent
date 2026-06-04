from typing import TypedDict, Dict, Any, List, Optional


class AgentState(TypedDict, total=False):
    """
    State for the Excel Processing Agent Graph.

    The agent processes uploaded Excel files through multiple stages:
    1. Loader: Triggers Glue job to process raw Excel
    2. Schema: Detects column types and patterns
    3. Cluster: Groups similar columns semantically
    4. Template: Generates downloadable templates
    5. Finalize: Prepares final results

    Optional transformation flow:
    - GlueExecutor: Executes user-requested transformations
    """

    # Required fields
    job_id: str
    s3_key: str
    next: str

    # Processing step tracking
    step: str

    # Data profiling results
    raw_profile: Dict[str, Any]
    cleaned_path: str
    columns: List[str]
    sample_data: List[Dict[str, Any]]

    # Schema detection
    schema: Dict[str, Any]

    # Clustering results
    clusters: Dict[str, Any]

    # Template generation
    templates: Dict[str, Any]
    template_files: List[Dict[str, str]]

    # Transformation handling
    user_request: Optional[str]
    glue_script: str
    glue_output: str
    transformed_path: Optional[str]
    transformation_explanation: Optional[str]

    # Results and errors
    results: Optional[Dict[str, Any]]
    error: Optional[str]