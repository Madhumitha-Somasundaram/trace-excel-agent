"""
Transformation Examples - Common PySpark patterns for user requests

These examples demonstrate how to handle common transformation requests:
- Unit conversions (m to km, kg to lbs, etc.)
- Filtering and aggregations
- Data cleaning and normalization
- Date operations
- Statistical calculations
"""

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, sum, avg, count, max, min, \
    round as spark_round, to_date, year, month, dayofweek, \
    trim, lower, upper, regexp_replace, coalesce


class TransformationExamples:
    """
    Collection of transformation patterns.

    These can be composed together based on user requests.
    """

    @staticmethod
    def convert_meters_to_kilometers(df: DataFrame, column_name: str) -> DataFrame:
        """
        Convert distance from meters to kilometers.

        Example: "Convert distance from meters to kilometers"
        """
        new_col_name = f"{column_name}_km"
        return df.withColumn(
            new_col_name,
            spark_round(col(column_name) / 1000, 2)
        )

    @staticmethod
    def convert_kilometers_to_miles(df: DataFrame, column_name: str) -> DataFrame:
        """
        Convert distance from kilometers to miles.

        Example: "Convert distance from km to miles"
        """
        new_col_name = f"{column_name}_miles"
        return df.withColumn(
            new_col_name,
            spark_round(col(column_name) * 0.621371, 2)
        )

    @staticmethod
    def convert_kilograms_to_pounds(df: DataFrame, column_name: str) -> DataFrame:
        """
        Convert weight from kg to lbs.

        Example: "Convert weight from kg to pounds"
        """
        new_col_name = f"{column_name}_lbs"
        return df.withColumn(
            new_col_name,
            spark_round(col(column_name) * 2.20462, 2)
        )

    @staticmethod
    def convert_celsius_to_fahrenheit(df: DataFrame, column_name: str) -> DataFrame:
        """
        Convert temperature from Celsius to Fahrenheit.

        Example: "Convert temperature to Fahrenheit"
        """
        new_col_name = f"{column_name}_fahrenheit"
        return df.withColumn(
            new_col_name,
            spark_round((col(column_name) * 9 / 5) + 32, 1)
        )

    @staticmethod
    def filter_by_status(df: DataFrame, status_column: str, status_value: str) -> DataFrame:
        """
        Filter rows by status.

        Example: "Filter rows where status is active"
        """
        return df.filter(col(status_column) == status_value)

    @staticmethod
    def filter_by_threshold(df: DataFrame, column_name: str, threshold: float, operator: str = '>') -> DataFrame:
        """
        Filter rows by numeric threshold.

        Example: "Filter rows where amount is greater than 1000"
        """
        if operator == '>':
            return df.filter(col(column_name) > threshold)
        elif operator == '<':
            return df.filter(col(column_name) < threshold)
        elif operator == '>=':
            return df.filter(col(column_name) >= threshold)
        elif operator == '<=':
            return df.filter(col(column_name) <= threshold)
        elif operator == '==':
            return df.filter(col(column_name) == threshold)
        else:
            return df

    @staticmethod
    def calculate_average_by_group(df: DataFrame, value_column: str, group_column: str) -> DataFrame:
        """
        Calculate average value by group.

        Example: "Calculate average salary by department"
        """
        return df.groupBy(group_column).agg(
            avg(value_column).alias(f"avg_{value_column}"),
            count("*").alias("count"),
            min(value_column).alias(f"min_{value_column}"),
            max(value_column).alias(f"max_{value_column}")
        )

    @staticmethod
    def calculate_total_by_group(df: DataFrame, value_column: str, group_column: str) -> DataFrame:
        """
        Calculate total (sum) by group.

        Example: "Calculate total revenue by product"
        """
        return df.groupBy(group_column).agg(
            sum(value_column).alias(f"total_{value_column}"),
            count("*").alias("count")
        )

    @staticmethod
    def remove_duplicates(df: DataFrame, subset_columns: list = None) -> DataFrame:
        """
        Remove duplicate rows.

        Example: "Remove duplicate rows"
        """
        if subset_columns:
            return df.dropDuplicates(subset_columns)
        return df.dropDuplicates()

    @staticmethod
    def fill_null_values(df: DataFrame, column_name: str, fill_value) -> DataFrame:
        """
        Fill null values with a specific value.

        Example: "Fill missing values in salary with 0"
        """
        return df.withColumn(
            column_name,
            coalesce(col(column_name), fill_value)
        )

    @staticmethod
    def standardize_text(df: DataFrame, column_name: str) -> DataFrame:
        """
        Standardize text: trim, lowercase, remove extra spaces.

        Example: "Standardize company names"
        """
        new_col = f"{column_name}_standardized"
        return df.withColumn(
            new_col,
            trim(lower(regexp_replace(col(column_name), '\\s+', ' ')))
        )

    @staticmethod
    def extract_date_components(df: DataFrame, date_column: str) -> DataFrame:
        """
        Extract year, month, day from date column.

        Example: "Extract year and month from order date"
        """
        return df \
            .withColumn(f"{date_column}_year", year(col(date_column))) \
            .withColumn(f"{date_column}_month", month(col(date_column))) \
            .withColumn(f"{date_column}_dayofweek", dayofweek(col(date_column)))

    @staticmethod
    def calculate_percentage(df: DataFrame, numerator_col: str, denominator_col: str) -> DataFrame:
        """
        Calculate percentage from two columns.

        Example: "Calculate completion rate percentage"
        """
        result_col = f"{numerator_col}_percentage"
        return df.withColumn(
            result_col,
            spark_round(
                (col(numerator_col) / col(denominator_col)) * 100,
                2
            )
        )

    @staticmethod
    def add_ranking(df: DataFrame, value_column: str, group_column: str = None) -> DataFrame:
        """
        Add ranking within groups.

        Example: "Rank employees by salary within each department"
        """
        from pyspark.sql.window import Window
        from pyspark.sql.functions import row_number, dense_rank

        if group_column:
            window_spec = Window.partitionBy(group_column).orderBy(col(value_column).desc())
        else:
            window_spec = Window.orderBy(col(value_column).desc())

        return df.withColumn("rank", dense_rank().over(window_spec))

    @staticmethod
    def pivot_data(df: DataFrame, index_col: str, pivot_col: str, value_col: str) -> DataFrame:
        """
        Pivot data from long to wide format.

        Example: "Pivot sales by month for each product"
        """
        return df.groupBy(index_col).pivot(pivot_col).sum(value_col)

    @staticmethod
    def combine_columns(df: DataFrame, columns: list, separator: str = ' ', result_col: str = 'combined') -> DataFrame:
        """
        Combine multiple columns into one.

        Example: "Combine first name and last name into full name"
        """
        from pyspark.sql.functions import concat_ws

        return df.withColumn(
            result_col,
            concat_ws(separator, *[col(c) for c in columns])
        )

    @staticmethod
    def calculate_moving_average(df: DataFrame, value_column: str, window_size: int = 3, order_column: str = None) -> DataFrame:
        """
        Calculate moving average.

        Example: "Calculate 7-day moving average of sales"
        """
        from pyspark.sql.window import Window
        from pyspark.sql.functions import avg

        if order_column:
            window_spec = Window.orderBy(order_column).rowsBetween(-window_size + 1, 0)
        else:
            window_spec = Window.rowsBetween(-window_size + 1, 0)

        return df.withColumn(
            f"{value_column}_moving_avg_{window_size}",
            spark_round(avg(col(value_column)).over(window_spec), 2)
        )

    @staticmethod
    def add_category_based_on_range(df: DataFrame, column_name: str, ranges: list, labels: list) -> DataFrame:
        """
        Categorize numeric values into ranges.

        Example: "Categorize age into groups (18-30: Young, 31-50: Middle, 51+: Senior)"

        Args:
            ranges: List of tuples [(min1, max1), (min2, max2), ...]
            labels: List of category labels matching ranges
        """
        category_col = f"{column_name}_category"

        # Build when conditions
        condition = None
        for (min_val, max_val), label in zip(ranges, labels):
            clause = (col(column_name) >= min_val) & (col(column_name) <= max_val)
            if condition is None:
                condition = when(clause, label)
            else:
                condition = condition.when(clause, label)

        return df.withColumn(category_col, condition.otherwise("Other"))


# Example usage patterns
TRANSFORMATION_PATTERNS = {
    "convert.*meters.*kilometers": "convert_meters_to_kilometers",
    "convert.*km.*miles": "convert_kilometers_to_miles",
    "convert.*kg.*pounds": "convert_kilograms_to_pounds",
    "convert.*celsius.*fahrenheit": "convert_celsius_to_fahrenheit",
    "filter.*status.*active": "filter_by_status",
    "average.*by": "calculate_average_by_group",
    "total.*by": "calculate_total_by_group",
    "remove.*duplicate": "remove_duplicates",
    "fill.*null|missing": "fill_null_values",
    "standardize.*text": "standardize_text",
    "extract.*date": "extract_date_components",
    "calculate.*percentage": "calculate_percentage",
    "rank.*by": "add_ranking",
    "pivot": "pivot_data",
    "combine.*columns": "combine_columns",
    "moving.*average": "calculate_moving_average",
    "categorize": "add_category_based_on_range"
}
