<div align="center">
  <img src="docs/sdg_logo.png" width="400" >
</div>

<div align="center">
<p align="center">

[![License](https://img.shields.io/badge/License-Apache%202-2162A3.svg)](https://www.apache.org/licenses/LICENSE-2.0.html)  [![CN doc](https://img.shields.io/badge/Readme-Simplified_Chinese-2162A3.svg)](README_ZH_CN.md)  [![slack](https://img.shields.io/badge/Slack-Join%20Chat-ff69b4.svg?style=flat-square)](https://join.slack.com/t/hitsz-ids/shared_invite/zt-2395mt6x2-dwf0j_423QkAgGvlNA5E1g)

# 🚀 Synthetic Data Generator

</p>
</div>

Synthetic Data Generator (SDG) is a framework focused on quickly generating high-quality structured tabular data. It supports more than 10 single-table and multi-table data synthesis algorithms, achieving up to 120 times performance improvement, and supports differential privacy and other methods to enhance the security of synthesized data.

Synthetic data is generated by machines based on real data and algorithms, it does not contain sensitive information, but can retain the characteristics of real data.
There is no correspondence between synthetic data and real data, and it is not subject to privacy regulations such as GDPR and ADPPA.
In practical applications, there is no need to worry about the risk of privacy leakage.
High-quality synthetic data can also be used in various fields such as data opening, model training and debugging, system development and testing, etc.


## 🎉 Features

+ high performance
   + SDG supports a variety of statistical methods, achieving up to 120 times faster execution speed, and reduces dependence on GPU devices;
   + SDG is optimized for large dataset, consumes less memory than other frameworks or GAN-based algorithms;
   + SDG will continue to track the latest progress in academia and industry, and introduce and support excellent algorithms and models in a timely manner.
+ Rapid deployment in production environment
   + Optimize for actual production needs, improve model performance, reduce memory overhead, and support practical features such as single machine multiple cards, multiple machines multiple cards;
   + Provide technologies required for production environments such as automated deployment, containerization, automated monitoring and alarming, and support rapid one-key deployment;
   + Specially optimized for load balancing and fault tolerance to improve high availability.
+ Privacy enhancements:
   + SDG supports differential privacy, anonymization and other methods to enhance the security of synthetic data.


## 🔛 Quick Start

### Local Install (Recommended)

At present, the code of this project is updated very quickly. We recommend that you use SDG by installing it through the source code.

```bash
git clone git@github.com:hitsz-ids/synthetic-data-generator.git
pip install -r requirement.txt
pip install .
```

### Install from PyPi

```bash
pip install sdgx
```

### Quick Demo of Single Table Data Generation

```python
# Import modules
from sdgx.models.single_table.ctgan import CTGAN
from sdgx.utils.io.csv_utils import *

# Read data from demo
demo_data, discrete_cols  = get_demo_single_table()
```

Real data are as follows：

```
       age  workclass  fnlwgt  ... hours-per-week  native-country  class
0       27    Private  177119  ...             44   United-States  <=50K
1       27    Private  216481  ...             40   United-States  <=50K
2       25    Private  256263  ...             40   United-States  <=50K
3       46    Private  147640  ...             40   United-States  <=50K
4       45    Private  172822  ...             76   United-States   >50K
...    ...        ...     ...  ...            ...             ...    ...
32556   43  Local-gov   33331  ...             40   United-States   >50K
32557   44    Private   98466  ...             35   United-States  <=50K
32558   23    Private   45317  ...             40   United-States  <=50K
32559   45  Local-gov  215862  ...             45   United-States   >50K
32560   25    Private  186925  ...             48   United-States  <=50K

[32561 rows x 15 columns]

```

```python
# Define model
model = CTGAN(epochs=10)
# Model training
model.fit(demo_data, discrete_cols)

# Generate synthetic data
sampled_data = model.generate(1000)
```

Synthetic data are as follows：

```
   age         workclass  fnlwgt  ... hours-per-week  native-country  class
0   33           Private  276389  ...             41   United-States   >50K
1   33  Self-emp-not-inc  296948  ...             54   United-States  <=50K
2   67       Without-pay  266913  ...             51        Columbia  <=50K
3   49           Private  423018  ...             41   United-States   >50K
4   22           Private  295325  ...             39   United-States   >50K
5   63           Private  234140  ...             65   United-States  <=50K
6   42           Private  243623  ...             52   United-States  <=50K
7   75           Private  247679  ...             41   United-States  <=50K
8   79           Private  332237  ...             41   United-States   >50K
9   28         State-gov  837932  ...             99   United-States  <=50K
```


## 🤝 Join Community

The SDG project was initiated by **Institute of Data Security, Harbin Institute of Technology**. If you are interested in out project, welcome to join our community. We welcome organizations, teams, and individuals who share our commitment to data protection and security through open source:

- Submit an issue by viewing [View First Good Issue](https://github.com/hitsz-ids/synthetic-data-generator/issues/new) or submit a Pull Request。
- For developer documentation, please see  [Develop documents].(./docs/develop/readme.md)

## 👩‍🎓 Related Work

### Research Paper

- CTGAN：[Modeling Tabular Data using Conditional GAN](https://proceedings.neurips.cc/paper/2019/hash/254ed7d2de3b23ab10936522dd547b78-Abstract.html)
- TVAE：[Modeling Tabular Data using Conditional GAN](https://proceedings.neurips.cc/paper/2019/hash/254ed7d2de3b23ab10936522dd547b78-Abstract.html)
- table-GAN：[Data Synthesis based on Generative Adversarial Networks](https://arxiv.org/pdf/1806.03384.pdf)
- CTAB-GAN:[CTAB-GAN: Effective Table Data Synthesizing](https://proceedings.mlr.press/v157/zhao21a/zhao21a.pdf)
- OCT-GAN: [OCT-GAN: Neural ODE-based Conditional Tabular GANs](https://arxiv.org/pdf/2105.14969.pdf)

### Dataset

- [Adult](http://archive.ics.uci.edu/ml/datasets/adult)
- [Satellite](http://archive.ics.uci.edu/dataset/146/statlog+landsat+satellite)
- [Rossmann](https://www.kaggle.com/competitions/rossmann-store-sales/data)
- [Telstra](https://www.kaggle.com/competitions/telstra-recruiting-network/data)


## 📄 License

The SDG open source project uses Apache-2.0 license, please refer to the [LICENSE].(https://github.com/hitsz-ids/synthetic-data-generator/blob/main/LICENSE)。
