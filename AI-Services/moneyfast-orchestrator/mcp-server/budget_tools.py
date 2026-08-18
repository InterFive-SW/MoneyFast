"""MoneyFast Budget and Expense Tools.

Bu modül, kullanıcının bütçe planlaması yapmasını ve harcama kayıtlarını ayrıştırmasını
sağlayan MCP araçlarını barındırır.
"""

from typing import Dict, Any
from mcp.server.fastmcp import FastMCP
import logging

log = logging.getLogger("moneyfast.mcp.budget")

def parse_expense(category: str, amount: float) -> Dict[str, Any]:
    """
    Kullanıcının harcama beyanını ayrıştırır ve standart formata dönüştürür.
    
    Args:
        category: Harcamanın kategorisi (örn: 'Market', 'Akaryakıt', 'Fatura').
        amount: Harcama tutarı (sayısal).
        
    Returns:
        Harcama detaylarını içeren JSON formatına uygun sözlük.
    """
    log.info("parse_expense called: category=%s, amount=%s", category, amount)
    return {
        "widget_type": "expense_action",
        "category": category.title(),
        "amount": float(amount)
    }

def calculate_budget(income: float) -> Dict[str, Any]:
    """
    Girilen toplam gelir üzerinden 50/30/20 kuralına göre bütçe planlaması yapar.
    - %50 İhtiyaçlar (Needs)
    - %30 İstekler (Wants)
    - %20 Tasarruf ve Yatırım (Savings)
    
    Args:
        income: Toplam aylık veya belirtilen dönemlik gelir.
        
    Returns:
        Bütçe dağılımını içeren JSON formatına uygun sözlük.
    """
    log.info("calculate_budget called: income=%s", income)
    return {
        "widget_type": "budget_plan",
        "income": float(income),
        "needs": round(income * 0.50, 2),
        "wants": round(income * 0.30, 2),
        "savings": round(income * 0.20, 2)
    }

def register(mcp: FastMCP) -> None:
    """Modüldeki araçları paylaşılan MCP sunucusuna kaydeder."""
    mcp.tool()(parse_expense)
    mcp.tool()(calculate_budget)
