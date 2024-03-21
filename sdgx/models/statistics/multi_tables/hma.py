from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Set
from collections import defaultdict

import numpy as np
import pandas as pd

from sdgx.models.statistics.multi_tables.base import MultiTableSynthesizerModel
from sdgx.models.statistics.single_table.copula import GaussianCopulaSynthesizer


class HMA(MultiTableSynthesizerModel):
    _synthesizer = GaussianCopulaSynthesizer
    """
    _synthesizer is the model used to fit each table, including parent and child tables.
    """

    _extended_columns: Dict = {}

    """
    _extended_columns is a dict, whose:
    - key is the child table and its foreign keys;
    - value is the extended columns, the parameter of the gaussian copula model,
      use the ._get_parameters() method;
    """
    DEFAULT_SYNTHESIZER_KWARGS = {
        'default_distribution': 'beta'
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_raw_data = True
        self._table_sizes = {}
        self._max_child_rows = {}
        self._augmented_tables = []
        self._learned_relationships = 0

    def _get_num_extended_columns(self, table_name, parent_table, columns_per_table):
        """Get the number of columns that will be generated for table_name.

        A table generates, for each foreign key:
            - 1 num_rows column
            - n*(n-1)/2 correlation columns for each data column
            - k parameter columns for each data column, where:
                - k = 4 if the distribution is beta or truncnorm (params are a, b, loc, scale)
                - k = 3 if the distribution is gamma (params are a, loc, scale)
                - k = 2 if the distribution is norm or uniform (params are loc, scale)
        """
        num_rows_columns = len(self._get_foreign_keys(parent_table, table_name))

        # no parameter columns are generated if there are no data columns
        num_data_columns = columns_per_table[table_name]
        if num_data_columns == 0:
            return num_rows_columns

        table_parameters = self.get_table_parameters(table_name)['table_parameters']
        distribution = table_parameters['default_distribution']
        num_parameters_columns = num_rows_columns * num_data_columns
        if distribution in {'beta', 'truncnorm'}:
            num_parameters_columns *= 4
        elif distribution == 'gamma':
            num_parameters_columns *= 3
        elif distribution in {'norm', 'uniform'}:
            num_parameters_columns *= 2

        num_correlation_columns = num_rows_columns * (num_data_columns - 1) * num_data_columns // 2

        return num_correlation_columns + num_rows_columns + num_parameters_columns

    def _estimate_columns_traversal(self, table_name, columns_per_table, visited):
        """Given a table, estimate how many columns each parent will model.
        确定有多少列要生成
        This method recursively models the children of a table all the way to the leaf nodes.

        Args:
            table_name (str):
                Name of the table to estimate the number of columns for.
            columns_per_table (dict):
                Dict that stores the number of data columns + extended columns for each table.
            visited (set):
                Set of table names that have already been visited.
        """
        for child_name in self.child_map[table_name]:
            if child_name not in visited:
                self._estimate_columns_traversal(child_name, columns_per_table, visited)

            columns_per_table[table_name] += \
                self._get_num_extended_columns(child_name, table_name, columns_per_table)

        visited.add(table_name)

    def _get_num_data_columns(self):
        """Get the number of data columns, ie colums that are not id, for each table."""
        columns_per_table = {}
        for table_name, table in self.tables.items():
            columns_per_table[table_name] = \
                sum([1 for col in table.columns.values() if col['sdtype'] != 'id'])

        return columns_per_table

    def _estimate_num_columns(self):
        """Estimate the number of columns that will be modeled for each table.

        This method estimates how many extended columns will be generated during the
        `_augment_tables` method, so it traverses the graph in the same way.
        If that method is ever changed, this should be updated to match.

        After running this method, `columns_per_table` will store an estimate of the
        total number of columns that each table has after running `_augment_tables`,
        that is, the number of extended columns generated by the child tables as well
        as the number of data columns in the table itself. `id` columns, like foreign
        and primary keys, are not counted since they are not modeled.

        Returns:
            dict:
                Dictionary of (table_name: int) mappings, indicating the estimated
                number of columns that will be modeled for each table.
        """
        # This dict will store the number of data columns + extended columns for each table
        # Initialize it with the number of data columns per table
        columns_per_table = self._get_num_data_columns()

        # Starting at root tables, recursively estimate the number of columns
        # each table will model
        visited = set()
        for table_name in self._get_root_parents():
            self._estimate_columns_traversal(table_name, columns_per_table, visited)

        return columns_per_table

    def preprocess(self, data):
        """Transform the raw data to numerical space.

        Args:
            data (dict):
                Dictionary mapping each table name to a ``pandas.DataFrame``.

        Returns:
            dict:
                A dictionary with the preprocessed data.
        """
        processed_data = super().preprocess(data)
        for _, synthesizer in self._table_synthesizers.items():
            #这里的resetsampling是否需要呢？
            synthesizer.reset_sampling()

        return processed_data

    # refer _get_extension in HMA.py
    def get_extended_columns(
            self,
            child_table_name: str,
            child_table: pd.DataFrame,
            foreign_key: str,
    ):
        """Calculate the extension columns for given child table.

        In this function, it is necessary to traverse each foreign key in the foreign key value,
        which shoud contained in resulting table.

        The values for a given index are generated by flattening a synthesizer fitted with
        the child rows with that foreign key value.

        Args:
            child_table_name (str): Name of the child table.
            tables_data_loader Dict(str, DataLoader): All table's dataloader.
            foreign_key (str): Foreign key of this child table.

        Returns:
            # NOTE Still Draft
            pd.DataFrame | Path: The extended table, without the parent table part
        """
        table_meta = self._table_synthesizers[child_table_name].get_metadata()

        extension_rows = []
        foreign_key_columns = self._get_all_foreign_keys(child_table_name)
        foreign_key_values = child_table[foreign_key].unique()
        child_table = child_table.set_index(foreign_key)

        index = []
        scale_columns = None
        for foreign_key_value in foreign_key_values:
            child_rows = child_table.loc[[foreign_key_value]]
            child_rows = child_rows[child_rows.columns.difference(foreign_key_columns)]

            try:
                if child_rows.empty:
                    row = pd.Series({'num_rows': len(child_rows)})
                    row.index = f'__{child_table_name}__{foreign_key}__' + row.index
                else:
                    synthesizer = self._synthesizer(
                        table_meta,
                        **self._table_parameters[child_table_name]
                    )
                    synthesizer.fit(child_rows.reset_index(drop=True))
                    row = synthesizer._get_parameters()
                    row = pd.Series(row)
                    row.index = f'__{child_table_name}__{foreign_key}__' + row.index

                    if scale_columns is None:
                        scale_columns = [
                            column
                            for column in row.index
                            if column.endswith('scale')
                        ]

                    if len(child_rows) == 1:
                        row.loc[scale_columns] = None

                extension_rows.append(row)
                index.append(foreign_key_value)
                self._extended_columns[child_table_name, foreign_key_value] = pd.DataFrame(extension_rows,
                                                                                           index=index)
            except Exception:
                pass

        return pd.DataFrame(extension_rows, index=index)

    @staticmethod
    def _clear_nans(table_data):
        for column in table_data.columns:
            column_data = table_data[column]
            if column_data.dtype in (int, float):
                fill_value = 0 if column_data.isna().all() else column_data.mean()
            else:
                fill_value = column_data.mode()[0]

            table_data[column] = table_data[column].fillna(fill_value)

    def get_extended_table(self, table, tables, table_name: str, disk_cache: bool = False):
        """Calculate the extension columns of the given table.

        For each of the table's foreign keys, generate the related extension columns,
        then extend the provided table.


        Returns:
            # NOTE Still draft
            pd.DataFrame | Path: the extended table after CPA.

        """
        self._table_sizes[table_name] = len(table)
        child_map = self.child_map[table_name]
        for child_name in child_map:
            if child_name not in self._augmented_tables:
                child_table = self.get_extended_table(tables[child_name], tables, child_name)
            else:
                child_table = tables[child_name]

            foreign_keys = self._get_foreign_keys(table_name, child_name)
            for foreign_key in foreign_keys:
                extension = self.get_extended_columns(child_name, child_table.copy(), foreign_key)
                for column in extension.columns:
                    extension[column] = extension[column].astype(float)
                    if extension[column].isna().all():
                        extension[column] = extension[column].fillna(1e-6)
                # rdt库在这里会把扩展表的数值全部转换成浮点数来适配，但需要解耦先不动它
                #     self.extended_columns[child_name][column] = FloatFormatter(
                #         enforce_min_max_values=True)
                #     self.extended_columns[child_name][column].fit(extension, column)
                table = table.merge(extension, how='left', right_index=True, left_index=True)

                num_rows_key = f'__{child_name}__{foreign_key}__num_rows'
                table[num_rows_key] = table[num_rows_key].fillna(0)
                self._max_child_rows[num_rows_key] = table[num_rows_key].max()

                tables[table_name] = table
                self._learned_relationships += 1

        self._augmented_tables.append(table_name)
        self._clear_nans(table)
        return table

    def get_extended_tables(self, processed_data):
        augmented_data = deepcopy(processed_data)
        self._augmented_tables = []
        self._learned_relationships = 0
        for table_name in processed_data:
            if not self.parent_map[table_name]:
                self.get_extended_table(augmented_data[table_name], augmented_data, table_name)

        return augmented_data

    def _pop_foreign_keys(self, table_data, table_name):
        """Remove foreign keys from the ``table_data``.
        移除外键列

        Args:
            table_data (pd.DataFrame):
                The table that contains the ``foreign_keys``.
            table_name (str):
                The name representing the table.

        Returns:
            keys (dict):
                A dictionary mapping with the foreign key and it's values within the table.
        """
        foreign_keys = self._get_all_foreign_keys(table_name)
        keys = {}
        for fk in foreign_keys:
            keys[fk] = table_data.pop(fk).to_numpy()

        return keys

    def model_tables(self, augmented_data):
        """model the augmented tables.

        Args:
            augmented_data (dict):
                Dictionary mapping each table name to an augmented ``pandas.DataFrame``.
        """

        augmented_data_to_model = [
            (table_name, table)
            for table_name, table in augmented_data.items()
            if table_name not in self.parent_map
        ]
        for table_name, table in augmented_data_to_model:
            keys = self._pop_foreign_keys(table, table_name)
            self._clear_nans(table)

            if not table.empty:
                self._table_synthesizers[table_name].fit(table)
                # 将移除的外键列重新添加到表格中。
            for name, values in keys.items():
                table[name] = values

    # ----------------------------------------------------------------------------------------------------

    def _extract_parameters(self, parent_row, table_name, foreign_key):
        """Get the params from a generated parent row.

        Args:
            parent_row (pandas.Series):
                A generated parent row.
            table_name (str):
                Name of the table to make the synthesizer for.
            foreign_key (str):
                Name of the foreign key used to form this
                parent child relationship.
        """
        prefix = f'__{table_name}__{foreign_key}__'
        keys = [key for key in parent_row.keys() if key.startswith(prefix)]
        new_keys = {key: key[len(prefix):] for key in keys}
        flat_parameters = parent_row[keys].astype(float).fillna(1e-6)

        num_rows_key = f'{prefix}num_rows'
        if num_rows_key in flat_parameters:
            num_rows = flat_parameters[num_rows_key]
            flat_parameters[num_rows_key] = min(
                self._max_child_rows[num_rows_key],
                round(num_rows)
            )

        flat_parameters = flat_parameters.to_dict()
        for parameter_name, parameter in flat_parameters.items():
            float_formatter = self.extended_columns[table_name][parameter_name]
            flat_parameters[parameter_name] = np.clip(
                parameter, float_formatter._min_value, float_formatter._max_value)

        return {new_keys[key]: value for key, value in flat_parameters.items()}

    def _recreate_child_synthesizer(self, child_name, parent_name, parent_row):
        # A child table is created based on only one foreign key.
        foreign_key = self._get_foreign_keys(parent_name, child_name)[0]
        parameters = self._extract_parameters(parent_row, child_name, foreign_key)
        table_meta = self.tables[child_name]

        synthesizer = self._synthesizer(table_meta, **self._table_parameters[child_name])
        synthesizer._set_parameters(parameters)
        # synthesizer._data_processor = self._table_synthesizers[child_name]._data_processor

        return synthesizer

    def _sample_rows(self, synthesizer, num_rows=None):
        """Sample ``num_rows`` from ``synthesizer``.

        Args:
            synthesizer (copula.multivariate.base):
                The fitted synthesizer for the table.
            num_rows (int or float):
                Number of rows to sample.

        Returns:
            pandas.DataFrame:
                Sampled rows, shape (, num_rows)
        """
        if num_rows is None:
            num_rows = synthesizer._num_rows
        return synthesizer.sample(int(num_rows), keep_extra_columns=True)

    def _get_num_rows_from_parent(self, parent_row, child_name, foreign_key):
        """Get the number of rows to sample for the child from the parent row."""
        num_rows_key = f'__{child_name}__{foreign_key}__num_rows'
        num_rows = 0
        if num_rows_key in parent_row.keys():
            num_rows = parent_row[num_rows_key]
            num_rows = min(
                self._max_child_rows[num_rows_key],
                round(num_rows)
            )

        return num_rows

    def _add_child_rows(self, child_name, parent_name, parent_row, sampled_data, num_rows=None):
        """Sample the child rows that reference the parent row.

        Args:
            child_name (str):
                The name of the child table.
            parent_name (str):
                The name of the parent table.
            parent_row (pd.Series):
                The row from the parent table to sample for from the child table.
            sampled_data (dict):
                A dictionary mapping table names to sampled data (pd.DataFrame).
            num_rows (int):
                Number of rows to sample. If None, infers number of child rows to sample
                from the parent row. Defaults to None.
        """
        # A child table is created based on only one foreign key.
        foreign_key = self._get_foreign_keys(parent_name, child_name)[0]
        if num_rows is None:
            num_rows = self._get_num_rows_from_parent(parent_row, child_name, foreign_key)
        child_synthesizer = self._recreate_child_synthesizer(child_name, parent_name, parent_row)

        sampled_rows = self._sample_rows(child_synthesizer, num_rows)

        if len(sampled_rows):
            parent_key = self.tables_data_frame[parent_name].primary_key
            if foreign_key in sampled_rows:
                # If foreign key is in sampeld rows raises `SettingWithCopyWarning
                row_indices = sampled_rows.index
                sampled_rows[foreign_key].iloc[row_indices] = parent_row[parent_key]
            else:
                sampled_rows[foreign_key] = parent_row[parent_key]

            previous = sampled_data.get(child_name)
            if previous is None:
                sampled_data[child_name] = sampled_rows
            else:
                sampled_data[child_name] = pd.concat(
                    [previous, sampled_rows]).reset_index(drop=True)

    def _sample_children(self, table_name, sampled_data):
        """Recursively sample the children of a table.

        This method will loop through the children of a table and sample rows for that child for
        every primary key value in the parent. If the child has already been sampled by another
        parent, this method will skip it.
        也就是说hma确实是只取序列中的第一个外键进行子表合成，其他父表直接跳过
        Args:
            table_name (string):
                Name of the table to sample children for.
            sampled_data (dict):
                A dictionary mapping table names to sampled tables (pd.DataFrame).
        """
        for child_name in self.child_map[table_name]:
            if child_name not in sampled_data:  # Sample based on only 1 parent
                for _, row in sampled_data[table_name].iterrows():
                    self._add_child_rows(
                        child_name=child_name,
                        parent_name=table_name,
                        parent_row=row,
                        sampled_data=sampled_data
                    )

                if child_name not in sampled_data:  # No child rows sampled, force row creation
                    foreign_key = self._get_foreign_keys(table_name, child_name)[0]
                    num_rows_key = f'__{child_name}__{foreign_key}__num_rows'
                    if num_rows_key in sampled_data[table_name].columns:
                        max_num_child_index = sampled_data[table_name][num_rows_key].idxmax()
                        parent_row = sampled_data[table_name].iloc[max_num_child_index]
                    else:
                        parent_row = sampled_data[table_name].sample().iloc[0]

                    self._add_child_rows(
                        child_name=child_name,
                        parent_name=table_name,
                        parent_row=parent_row,
                        sampled_data=sampled_data,
                        num_rows=1
                    )
                self._sample_children(table_name=child_name, sampled_data=sampled_data)

    def _finalize(self, sampled_data):
        """Remove extra columns from sampled tables and apply finishing touches.

        This method reverts the previous transformations to go back
        to values in the original space.

        Args:
            sampled_data (dict):
                Dictionary mapping table names to sampled tables (pd.DataFrame)

        Returns:
            Dictionary mapping table names to their formatted sampled tables.
        """
        final_data = {}
        for table_name, table_rows in sampled_data.items():
            synthesizer = self._table_synthesizers.get(table_name)
            # 这里会把生成的数据用dataprocesseor在preprocess阶段存储的对应类型还原回去，待实现
            dtypes = synthesizer._data_processor._dtypes
            for name, dtype in dtypes.items():
                table_rows[name] = table_rows[name].dropna().astype(dtype)

            final_data[table_name] = table_rows[list(dtypes.keys())]

        return final_data

    def sample(self, count=1.0, *args, **kwargs):
        """Sample the entire dataset.

        Returns a dictionary with all the tables of the dataset. The amount of rows sampled will
        depend from table to table. This is because the children tables are created modelling the
        relation that they have with their parent tables, so its behavior may change from one
        table to another.


        Returns:
            dict:
                A dictionary containing as keys the names of the tables and as values the
                sampled data tables as ``pandas.DataFrame``.
        """
        sampled_data = {}

        # DFS to sample roots and then their children
        non_root_parents = set(self.parent_map.keys())
        root_parents = set(self.tables.keys()) - non_root_parents
        for table in root_parents:
            num_rows = int(self._table_sizes[table] * count)
            synthesizer = self._table_synthesizers[table]
            sampled_data[table] = self._sample_rows(synthesizer, num_rows)
            self._sample_children(table_name=table, sampled_data=sampled_data)

        added_relationships = set()
        for relationship in self.metadata_combiner.relationships:
            parent_name = relationship.parent_table
            child_name = relationship.child_table
            # When more than one relationship exists between two tables, only the first one
            # is used to recreate the child tables, so the rest can be skipped.
            if (parent_name, child_name) not in added_relationships:
                self._add_foreign_key_columns(
                    sampled_data[child_name],
                    sampled_data[parent_name],
                    child_name,
                    parent_name
                )
                added_relationships.add((parent_name, child_name))

        return self._finalize(sampled_data)

    # ----------------------------------------------------------------------------------------------------

    @staticmethod
    def _find_parent_id(likelihoods, num_rows):
        """Find the parent id for one row based on the likelihoods of parent id values.

        If likelihoods are invalid, fall back to the num_rows.

        Args:
            likelihoods (pandas.Series):
                The likelihood of parent id values.
            num_rows (pandas.Series):
                The number of times each parent id value appears in the data.

        Returns:
            int:
                The parent id for this row, chosen based on likelihoods.
        """
        mean = likelihoods.mean()
        if (likelihoods == 0).all():
            # All rows got 0 likelihood, fallback to num_rows
            likelihoods = num_rows
        elif pd.isna(mean) or mean == 0:
            # Some rows got singular matrix error and the rest were 0
            # Fallback to num_rows on the singular matrix rows and
            # keep 0s on the rest.
            likelihoods = likelihoods.fillna(num_rows)
        else:
            # at least one row got a valid likelihood, so fill the
            # rows that got a singular matrix error with the mean
            likelihoods = likelihoods.fillna(mean)

        total = likelihoods.sum()
        if total == 0:
            # Worse case scenario: we have no likelihoods
            # and all num_rows are 0, so we fallback to uniform
            length = len(likelihoods)
            weights = np.ones(length) / length
        else:
            weights = likelihoods.to_numpy() / total

        return np.random.choice(likelihoods.index.to_list(), p=weights)

    def _get_likelihoods(self, table_rows, parent_rows, table_name, foreign_key):
        """Calculate the likelihood of each parent id value appearing in the data.

        Args:
            table_rows (pandas.DataFrame):
                The rows in the child table.
            parent_rows (pandas.DataFrame):
                The rows in the parent table.
            table_name (str):
                The name of the child table.
            foreign_key (str):
                The foreign key column in the child table.

        Returns:
            pandas.DataFrame:
                A DataFrame of the likelihood of each parent id.
        """
        likelihoods = {}
        table_rows = table_rows.copy()
        #dataprocessor实现问题
        data_processor = self._table_synthesizers[table_name]._data_processor
        transformed = data_processor.transform(table_rows)
        if transformed.index.name:
            table_rows = table_rows.set_index(transformed.index.name)

        table_rows = pd.concat(
            [transformed, table_rows.drop(columns=transformed.columns)],
            axis=1
        )
        for parent_id, row in parent_rows.iterrows():
            parameters = self._extract_parameters(row, table_name, foreign_key)
            table_meta = self._table_synthesizers[table_name].get_metadata()
            synthesizer = self._synthesizer(table_meta, **self._table_parameters[table_name])
            synthesizer._set_parameters(parameters)
            try:
                likelihoods[parent_id] = synthesizer._get_likelihood(table_rows)

            except (AttributeError, np.linalg.LinAlgError):
                likelihoods[parent_id] = None

        return pd.DataFrame(likelihoods, index=table_rows.index)

    def _find_parent_ids(self, child_table, parent_table, child_name, parent_name, foreign_key):
        """Find parent ids for the given table and foreign key.

        The parent ids are chosen randomly based on the likelihood of the available
        parent ids in the parent table.

        Args:
            child_table (pd.DataFrame):
                The child table dataframe.
            parent_table (pd.DataFrame):
                The parent table dataframe.
            child_name (str):
                The name of the child table.
            foreign_key (str):
                The name of the foreign key column in the child table.

        Returns:
            pandas.Series:
                The parent ids for the given table data.
        """
        # Create a copy of the parent table with the primary key as index to calculate likelihoods
        primary_key = self.tables[parent_name].primary_key
        parent_table = parent_table.set_index(primary_key)
        num_rows = parent_table[f'__{child_name}__{foreign_key}__num_rows'].fillna(0).clip(0)

        likelihoods = self._get_likelihoods(child_table, parent_table, child_name, foreign_key)
        return likelihoods.apply(self._find_parent_id, axis=1, num_rows=num_rows)

    def _add_foreign_key_columns(self, child_table, parent_table, child_name, parent_name):
        for foreign_key in self._get_foreign_keys(parent_name, child_name):
            if foreign_key not in child_table:
                parent_ids = self._find_parent_ids(
                    child_table=child_table,
                    parent_table=parent_table,
                    child_name=child_name,
                    parent_name=parent_name,
                    foreign_key=foreign_key
                )
                child_table[foreign_key] = parent_ids.to_numpy()
# ----------------------------------------------------------------------------------------------------
