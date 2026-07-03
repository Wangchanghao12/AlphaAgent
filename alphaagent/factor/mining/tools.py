"""LLM 评估与交付工具：train/val 评估 + submit_factor 入库。"""



from __future__ import annotations



import json

from pathlib import Path

from typing import Any



from alphaagent.factor.mining.schemas import EvalTrainRequest, EvalValRequest

from alphaagent.factor.mining.service import StockEvalService

from alphaagent.factor.mining.submit import FactorSubmitService



_EVAL_PARAMETERS: dict[str, Any] = {

    "type": "object",

    "properties": {

        "multi_line_expr": {

            "type": "string",

            "description": "多行因子 DSL：可含赋值行，最后一行为因子值；列用 $列名 引用，算子大写。",

        },

        "factor_name": {"type": "string", "description": "因子列逻辑名，默认 expr。"},

        "include_detail_tables": {

            "type": "boolean",

            "description": "true 时额外返回 by_month / by_symbol 明细；默认 false 仅返回 summary。",

            "default": False,

        },

        "label_quantile_n": {

            "type": "integer",

            "description": "按因子值等频分位分桶，输出每桶 label 均值；0 表示不计算。默认 10。",

            "default": 10,

        },

    },

    "required": ["multi_line_expr"],

    "additionalProperties": False,

}



_VAL_PARAMETERS: dict[str, Any] = {

    "type": "object",

    "properties": {

        **_EVAL_PARAMETERS["properties"],

        "expected_sign": {

            "type": "integer",

            "description": "train summary.ic 的符号（1=正、-1=负）；传入后返回 sign_check。",

            "enum": [1, -1],

        },

    },

    "required": ["multi_line_expr"],

    "additionalProperties": False,

}



_SUBMIT_PARAMETERS: dict[str, Any] = {

    "type": "object",

    "properties": {

        "multi_line_expr": {

            "type": "string",

            "description": "与 train/val 评估一致的多行因子 DSL。",

        },

        "factor_name": {

            "type": "string",

            "description": "因子唯一逻辑名（蛇形英文），将写入因子库 factor_id。",

        },

        "comment": {

            "type": "string",

            "description": "因子含义说明：经济直觉、关键算子与窗口、预期 IC 方向等，供后续查阅。",

        },

    },

    "required": ["multi_line_expr", "factor_name", "comment"],

    "additionalProperties": False,

}



TOOL_NAMES = ("eval_on_train_set", "eval_on_val_set", "submit_factor")





class FactorEvalTools:

    """持有一个已建会话，向 LLM 暴露 eval_on_train_set / eval_on_val_set / submit_factor。"""



    def __init__(

        self,

        service: StockEvalService,

        session_id: str,

        *,

        submit_service: FactorSubmitService | None = None,

    ) -> None:

        self.service = service

        self.session_id = session_id

        self.submit_service = submit_service



    def schemas(self) -> list[dict[str, Any]]:

        out = [

            {

                "type": "function",

                "function": {

                    "name": "eval_on_train_set",

                    "description": "训练集评估多行因子表达式，返回 summary、monthly_corr_robustness、label_quantile_buckets。",

                    "parameters": _EVAL_PARAMETERS,

                },

            },

            {

                "type": "function",

                "function": {

                    "name": "eval_on_val_set",

                    "description": "验证集评估；须传 expected_sign（train IC 符号 1/-1），结果含 sign_check。",

                    "parameters": _VAL_PARAMETERS,

                },

            },

        ]

        if self.submit_service is not None:

            out.append(

                {

                    "type": "function",

                    "function": {

                        "name": "submit_factor",

                        "description": (

                            "【正式交付】将保留级候选入库 factorzoo：train-start~val-end 全区间求值，"

                            "检查 IC/ICIR/coverage/cs_pearson_autocorr（>0.6）与截面去重；成功后 stored=true。"

                            "train/val 达标后必须调用本工具完成交付，不可仅文字总结。"

                            "查重失败时返回 top_neighbors 含相似因子 expr。"

                        ),

                        "parameters": _SUBMIT_PARAMETERS,

                    },

                }

            )

        return out



    def dispatch(self, name: str, arguments: Any) -> dict[str, Any]:

        if isinstance(arguments, str):

            try:

                arguments = json.loads(arguments) if arguments.strip() else {}

            except json.JSONDecodeError as e:

                return {"ok": False, "error": f"invalid_tool_arguments_json: {e}", "error_type": "JSONDecodeError"}

        if not isinstance(arguments, dict):

            return {"ok": False, "error": "tool_arguments_must_be_object", "error_type": "ToolArgumentsError"}



        if name == "submit_factor":

            return self._dispatch_submit(arguments)



        expr = arguments.get("multi_line_expr")

        if not isinstance(expr, str) or not expr.strip():

            return {"ok": False, "error": "multi_line_expr_required_non_empty_string", "error_type": "ToolArgumentsError"}



        factor_name = arguments.get("factor_name") or "expr"

        include_detail = bool(arguments.get("include_detail_tables", False))

        label_quantile_n = arguments.get("label_quantile_n", 10)

        if label_quantile_n is None:

            label_quantile_n = 10



        if name == "eval_on_train_set":

            return self.service.eval_train(

                EvalTrainRequest(

                    session_id=self.session_id,

                    multi_line_expr=expr,

                    factor_name=factor_name,

                    include_detail_tables=include_detail,

                    label_quantile_n=int(label_quantile_n),

                )

            )

        if name == "eval_on_val_set":

            expected_sign = arguments.get("expected_sign")

            if expected_sign not in (None, 1, -1):

                return {"ok": False, "error": "expected_sign_must_be_1_or_-1", "error_type": "ToolArgumentsError"}

            return self.service.eval_val(

                EvalValRequest(

                    session_id=self.session_id,

                    multi_line_expr=expr,

                    factor_name=factor_name,

                    include_detail_tables=include_detail,

                    label_quantile_n=int(label_quantile_n),

                    expected_sign=expected_sign,

                )

            )

        return {"ok": False, "error": f"unknown_tool: {name}", "error_type": "UnknownTool"}



    def _dispatch_submit(self, arguments: dict[str, Any]) -> dict[str, Any]:

        if self.submit_service is None:

            return {

                "ok": False,

                "stored": False,

                "error": "submit_factor_disabled",

                "error_type": "SubmitDisabled",

            }

        expr = arguments.get("multi_line_expr")

        factor_name = arguments.get("factor_name")

        comment = arguments.get("comment")

        if not isinstance(factor_name, str) or not factor_name.strip():

            return {

                "ok": False,

                "stored": False,

                "error": "factor_name_required_non_empty_string",

                "error_type": "ToolArgumentsError",

            }

        if not isinstance(comment, str) or not comment.strip():

            return {

                "ok": False,

                "stored": False,

                "error": "comment_required_non_empty_string",

                "error_type": "ToolArgumentsError",

            }

        return self.submit_service.submit(

            self.session_id,

            multi_line_expr=str(expr or ""),

            factor_name=factor_name.strip(),

            comment=comment.strip(),

        )



    @staticmethod

    def result_to_content(result: dict[str, Any]) -> str:

        return json.dumps(result, ensure_ascii=False, default=str)


